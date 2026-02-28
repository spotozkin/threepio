"""RVC v2 voice converter: python backend (rvc_python) or cli backend (subprocess)."""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

RVC_TOOLS_RVC_MISSING = """
RVC CLI backend requires the RVC repo at tools/rvc/. It was not found.

To set up:
  1. brew install ffmpeg
  2. git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI tools/rvc
  3. cd tools/rvc && pip install -r requirements.txt

Alternatively, use the python backend: set RVC_BACKEND=python and
  pip install -e ".[rvc]"
"""


class RVCConverter:
    """RVC v2 voice conversion: input WAV bytes -> output WAV bytes."""

    def __init__(
        self,
        model_path: str,
        index_path: str = "",
        pitch_shift: int = 0,
        f0_method: str = "rmvpe",
        sample_rate: int = 48000,
        device: str = "cpu",
        cache_warmup: bool = True,
        backend: str = "cli",
        cli_path: str = "tools/rvc_infer.py",
        python_module: str = "rvc_python",
    ) -> None:
        self._model_path = Path(model_path).resolve()
        self._index_path = Path(index_path).resolve() if index_path.strip() else None
        self._pitch_shift = pitch_shift
        self._f0_method = f0_method
        self._sample_rate = sample_rate
        self._device = device
        self._cache_warmup = cache_warmup
        self._backend = backend
        self._cli_path = cli_path
        self._python_module = python_module
        self._rvc = None
        # Project root: .../src/threepio/speech/rvc -> .../ (dir containing pyproject.toml)
        self._project_root = Path(__file__).resolve().parents[4]
        self._load_model()

    def _map_device(self) -> str:
        """Map device to rvc-python format (cpu:0, cuda:0). MPS falls back to CPU."""
        if self._device == "cuda":
            return "cuda:0"
        return "cpu:0"

    def _load_model(self) -> None:
        """Load RVC model (python backend) or validate CLI (cli backend)."""
        if not self._model_path.exists():
            raise FileNotFoundError(f"RVC model not found: {self._model_path}")

        if self._backend == "python":
            self._load_python_backend()
        else:
            self._validate_cli_backend()

    def _load_python_backend(self) -> None:
        """Load rvc_python in-process."""
        try:
            mod = __import__(self._python_module)
        except ImportError as e:
            raise ImportError(
                f"RVC python backend requires {self._python_module}. "
                f"Install with: pip install -e \".[rvc]\" or pip install {self._python_module}"
            ) from e

        try:
            from rvc_python.infer import RVCInference
        except ImportError as e:
            raise ImportError(
                f"RVC python backend: {self._python_module}.infer not found. "
                f"Install: pip install {self._python_module}"
            ) from e

        device_str = self._map_device()
        index_str = str(self._index_path) if self._index_path and self._index_path.exists() else ""
        self._rvc = RVCInference(
            device=device_str,
            model_path=str(self._model_path),
            index_path=index_str,
            version="v2",
        )
        self._rvc.set_params(
            f0up_key=self._pitch_shift,
            f0method=self._f0_method,
            index_rate=0.75 if index_str else 0.5,
            resample_sr=self._sample_rate if self._sample_rate > 0 else 0,
        )
        logger.info("[RVC] Loaded model %s (index=%s) [python backend]", self._model_path, bool(index_str))
        if self._cache_warmup:
            self._do_warmup()

    def _validate_cli_backend(self) -> None:
        """Validate CLI script, tools/rvc, and that selected Python can import torch."""
        cli_full = (self._project_root / self._cli_path).resolve()
        if not cli_full.exists():
            raise FileNotFoundError(
                f"RVC CLI script not found: {cli_full}\n{RVC_TOOLS_RVC_MISSING}"
            )
        rvc_repo = self._project_root / "tools" / "rvc"
        if not rvc_repo.is_dir():
            raise FileNotFoundError(
                f"RVC repo not found at tools/rvc/\n{RVC_TOOLS_RVC_MISSING}"
            )
        logger.info("[RVC] Using CLI backend (tools/rvc_infer.py)")
        self._check_cli_python_can_import_torch()

    def _check_cli_python_can_import_torch(self) -> None:
        """Verify the CLI Python can import torch; raise helpful error if not."""
        python_exe, subprocess_env = self._get_cli_python_and_env()
        result = subprocess.run(
            [python_exe, "-c", "import torch"],
            capture_output=True,
            text=True,
            timeout=10,
            env=subprocess_env,
        )
        if result.returncode != 0:
            err = result.stderr or result.stdout or "(no output)"
            raise RuntimeError(
                f"RVC CLI Python cannot import torch: {python_exe}\n"
                f"Error: {err}\n"
                "Ensure tools/rvc/.venv has torch (pip install -r requirements.txt in tools/rvc) "
                "or set RVC_CLI_PYTHON to a Python that has torch."
            )

    def _do_warmup(self) -> None:
        """Run a minimal inference to warm up model cache (python backend only)."""
        if self._rvc is None:
            return
        try:
            import io

            import numpy as np
            from scipy.io import wavfile

            sr = 24000
            samples = int(0.1 * sr)
            audio = np.zeros(samples, dtype=np.int16)
            buf = io.BytesIO()
            wavfile.write(buf, sr, audio)
            buf.seek(0)
            _ = self.convert_wav_bytes(buf.read())
            logger.debug("[RVC] Cache warmup done")
        except Exception as e:
            logger.debug("[RVC] Warmup skipped: %s", e)

    def _get_cli_python_and_env(self) -> tuple[str, dict[str, str]]:
        """Resolve Python for RVC CLI and subprocess env. Priority: RVC_CLI_PYTHON > tools/rvc/.venv/bin/python > sys.executable."""
        rvc_py = os.environ.get("RVC_CLI_PYTHON")
        default = self._project_root / "tools" / "rvc" / ".venv" / "bin" / "python"
        if not rvc_py and default.exists():
            rvc_py = str(default.resolve())
        if not rvc_py:
            rvc_py = sys.executable

        logger.info("[RVC] CLI python=%s", rvc_py)

        env = os.environ.copy()
        venv_bin = default.parent
        if venv_bin.exists():
            path_prepend = str(venv_bin.resolve())
            env["PATH"] = f"{path_prepend}:{env.get('PATH', '')}"

        return rvc_py, env

    def _convert_cli(self, input_wav_bytes: bytes) -> bytes:
        """Run CLI backend via subprocess."""
        cli_full = (self._project_root / self._cli_path).resolve()
        python_exe, subprocess_env = self._get_cli_python_and_env()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
            fin.write(input_wav_bytes)
            in_path = fin.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
                out_path = fout.name
            try:
                cmd = [
                    python_exe,
                    str(cli_full),
                    "--model", str(self._model_path),
                    "--in", in_path,
                    "--out", out_path,
                    "--pitch", str(self._pitch_shift),
                    "--f0", self._f0_method,
                    "--sr", str(self._sample_rate),
                    "--device", self._device,
                ]
                if self._index_path and self._index_path.exists():
                    cmd.extend(["--index", str(self._index_path)])
                result = subprocess.run(
                    cmd,
                    cwd=str(self._project_root),
                    env=subprocess_env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    err_detail = result.stderr or result.stdout or "(no output)"
                    raise RuntimeError(
                        f"RVC CLI failed (python={python_exe}): {err_detail}"
                    )
                return Path(out_path).read_bytes()
            finally:
                Path(out_path).unlink(missing_ok=True)
        finally:
            Path(in_path).unlink(missing_ok=True)

    def convert_wav_bytes(self, input_wav_bytes: bytes) -> bytes:
        """Convert input WAV bytes to RVC-processed WAV bytes."""
        if self._backend == "cli":
            return self._convert_cli(input_wav_bytes)
        if self._rvc is None:
            raise RuntimeError("RVC model not loaded")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
            fin.write(input_wav_bytes)
            in_path = fin.name
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fout:
                out_path = fout.name
            try:
                self._rvc.infer_file(in_path, out_path)
                return Path(out_path).read_bytes()
            finally:
                Path(out_path).unlink(missing_ok=True)
        finally:
            Path(in_path).unlink(missing_ok=True)


def get_rvc_converter_or_none():
    """Return RVCConverter if ENABLE_RVC and paths valid, else None."""
    from threepio.config import get_settings

    s = get_settings()
    if not s.ENABLE_RVC or not s.RVC_MODEL_PATH.strip():
        return None
    model_path = Path(s.RVC_MODEL_PATH).resolve()
    if not model_path.exists():
        logger.warning("[RVC] ENABLE_RVC=1 but RVC_MODEL_PATH=%s not found", model_path)
        return None
    try:
        return RVCConverter(
            model_path=str(model_path),
            index_path=s.RVC_INDEX_PATH.strip() or "",
            pitch_shift=s.RVC_PITCH_SHIFT,
            f0_method=s.RVC_F0_METHOD,
            sample_rate=s.RVC_SAMPLE_RATE,
            device=s.RVC_DEVICE,
            cache_warmup=s.RVC_CACHE_WARMUP,
            backend=s.RVC_BACKEND,
            cli_path=s.RVC_CLI_PATH,
            python_module=s.RVC_PYTHON_MODULE,
        )
    except Exception as e:
        logger.warning("[RVC] Failed to load: %s", e)
        return None
