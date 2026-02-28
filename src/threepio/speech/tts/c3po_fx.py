"""C-3PO voice post-processing via ffmpeg: canonical _AB_fix1 chain + optional robot_v1 character layer."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _debug_enabled() -> bool:
    v = os.environ.get("THREEPIO_DEBUG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


# ffmpeg atempo supports 0.5–2.0 (preserves pitch)
ATEMPO_MIN, ATEMPO_MAX = 0.5, 2.0

# ffmpeg acompressor threshold is linear amplitude, not dB; valid range
ACCOMPRESSOR_THRESHOLD_MIN = 0.000976563
ACCOMPRESSOR_THRESHOLD_MAX = 1.0

# Canonical _AB_fix1 (from zsh history): volume=0.95, highpass=110, lowpass=12000,
# acompressor -20dB ratio=3 attack=5 release=90, aecho=0.6:0.75:14|28:0.18|0.12, alimiter=0.95
AB_FIX1_VOLUME = 0.95
AB_FIX1_HIGHPASS = 110
AB_FIX1_LOWPASS = 12000
AB_FIX1_COMP_THRESHOLD_DB = -20.0
AB_FIX1_COMP_RATIO = 3
AB_FIX1_COMP_ATTACK = 5
AB_FIX1_COMP_RELEASE = 90
AB_FIX1_ECHO_IN = 0.6
AB_FIX1_ECHO_OUT = 0.75
AB_FIX1_ECHO_DELAYS = "14|28"
AB_FIX1_ECHO_DECAYS = "0.18|0.12"
AB_FIX1_LIMIT = 0.95

# robot_v1: ringmod + chorus (from history)
ROBOT_V1_RINGMOD_FREQ = 35
ROBOT_V1_RINGMOD_MIX = 0.18
ROBOT_V1_CHORUS = "0.6:0.9:10:0.5:0.28:0.22"  # in:out:delays:decays:speeds:depths

# Do not change without updating tests and bumping FX version.
C3PO_FX_VERSION = "v1.0.0"


def _db_to_linear_threshold(db: float) -> float:
    """Convert dB to linear amplitude for ffmpeg acompressor; clamp to valid range."""
    linear = 10.0 ** (float(db) / 20.0)
    return max(ACCOMPRESSOR_THRESHOLD_MIN, min(ACCOMPRESSOR_THRESHOLD_MAX, linear))


def _build_canonical_ab_fix1_chain() -> str:
    """Build the exact _AB_fix1 filter chain from constants only (no settings). Used for signature lock-in."""
    thresh = _db_to_linear_threshold(AB_FIX1_COMP_THRESHOLD_DB)
    return (
        f"volume={AB_FIX1_VOLUME},"
        f"highpass=f={AB_FIX1_HIGHPASS},"
        f"lowpass=f={AB_FIX1_LOWPASS},"
        f"acompressor=threshold={thresh}:ratio={AB_FIX1_COMP_RATIO}:attack={AB_FIX1_COMP_ATTACK}:release={AB_FIX1_COMP_RELEASE},"
        f"aecho={AB_FIX1_ECHO_IN}:{AB_FIX1_ECHO_OUT}:{AB_FIX1_ECHO_DELAYS}:{AB_FIX1_ECHO_DECAYS},"
        f"alimiter=limit={AB_FIX1_LIMIT}"
    )


# Lock-in: canonical chain at style=ab_fix1, intensity=1.0, speed=1.0. Do not change without updating tests and bumping FX version.
CANONICAL_AB_FIX1_SIGNATURE = _build_canonical_ab_fix1_chain()


def get_ab_fix1_chain_signature() -> str:
    """Return signature for the currently-built chain when style=ab_fix1 and intensity=1.0 (uses settings)."""
    return build_c3po_fx_chain(intensity=1.0, speed=1.0)


def _atempo_filter(speed: float) -> str:
    """Build atempo filter; preserves pitch. Raises if speed not in 0.5–2.0."""
    s = float(speed)
    if not (ATEMPO_MIN <= s <= ATEMPO_MAX):
        raise ValueError(
            f"atempo speed must be in [{ATEMPO_MIN}, {ATEMPO_MAX}]; got {s}. "
            "Chain multiple atempo for values outside range."
        )
    return f"atempo={s}"


def _get_c3po_params():
    """Load C3PO FX params from settings. For ab_fix1 style uses canonical values; settings override when style allows."""
    from threepio.config.settings import get_settings

    s = get_settings()
    style = (getattr(s, "C3PO_FX_STYLE", None) or "ab_fix1").strip().lower()
    if style == "ab_fix1":
        volume = getattr(s, "C3PO_FX_VOLUME", AB_FIX1_VOLUME)
        highpass = getattr(s, "C3PO_FX_HIGHPASS", AB_FIX1_HIGHPASS)
        lowpass = getattr(s, "C3PO_FX_LOWPASS", AB_FIX1_LOWPASS)
        comp_db = getattr(s, "C3PO_FX_COMP_THRESHOLD_DB", AB_FIX1_COMP_THRESHOLD_DB)
        comp_ratio = getattr(s, "C3PO_FX_COMP_RATIO", AB_FIX1_COMP_RATIO)
        comp_attack = getattr(s, "C3PO_FX_COMP_ATTACK", AB_FIX1_COMP_ATTACK)
        comp_release = getattr(s, "C3PO_FX_COMP_RELEASE", AB_FIX1_COMP_RELEASE)
        echo_in = getattr(s, "C3PO_ECHO_IN", AB_FIX1_ECHO_IN)
        echo_out = getattr(s, "C3PO_ECHO_OUT", AB_FIX1_ECHO_OUT)
        echo_delays = getattr(s, "C3PO_ECHO_DELAYS", AB_FIX1_ECHO_DELAYS)
        echo_decays = getattr(s, "C3PO_ECHO_DECAYS", AB_FIX1_ECHO_DECAYS)
        limit = getattr(s, "C3PO_LIMIT", AB_FIX1_LIMIT)
    else:
        volume = s.C3PO_FX_VOLUME
        highpass = s.C3PO_FX_HIGHPASS
        lowpass = s.C3PO_FX_LOWPASS
        comp_db = s.C3PO_FX_COMP_THRESHOLD_DB
        comp_ratio = s.C3PO_FX_COMP_RATIO
        comp_attack = s.C3PO_FX_COMP_ATTACK
        comp_release = s.C3PO_FX_COMP_RELEASE
        echo_in = s.C3PO_ECHO_IN
        echo_out = s.C3PO_ECHO_OUT
        echo_delays = s.C3PO_ECHO_DELAYS
        echo_decays = s.C3PO_ECHO_DECAYS
        limit = s.C3PO_LIMIT

    comp_threshold_linear = _db_to_linear_threshold(comp_db)
    return {
        "volume": volume,
        "highpass": highpass,
        "lowpass": lowpass,
        "comp_threshold": comp_threshold_linear,
        "comp_ratio": comp_ratio,
        "comp_attack": comp_attack,
        "comp_release": comp_release,
        "echo_in": echo_in,
        "echo_out": echo_out,
        "echo_delays": echo_delays,
        "echo_decays": echo_decays,
        "limit": limit,
        "style": style,
    }


def build_c3po_fx_chain(intensity: float = 1.0, speed: float = 1.0) -> str:
    """
    Build the C3PO FX filter chain. At style=ab_fix1 and intensity=1.0 reproduces _AB_fix1 exactly.
    robot_v1 appends ringmod + chorus; intensity scales robot layer mix amounts.
    """
    p = _get_c3po_params()
    i = max(0.0, min(2.0, float(intensity)))
    style = p.get("style", "ab_fix1")

    # Scale echo decays by intensity when != 1.0 (ab_fix1 stays stable at 1.0)
    if i == 1.0:
        echo_decays = p["echo_decays"]
    else:
        parts = p["echo_decays"].split("|")
        scaled = []
        for part in parts:
            try:
                val = float(part.strip())
                scaled.append(str(round(val * i, 4)))
            except (ValueError, TypeError):
                scaled.append(part)
        echo_decays = "|".join(scaled)

    ratio_str = str(int(p["comp_ratio"])) if p["comp_ratio"] == int(p["comp_ratio"]) else str(p["comp_ratio"])
    core = (
        f"volume={p['volume']},"
        f"highpass=f={p['highpass']},"
        f"lowpass=f={p['lowpass']},"
        f"acompressor=threshold={p['comp_threshold']}:ratio={ratio_str}:attack={p['comp_attack']}:release={p['comp_release']},"
        f"aecho={p['echo_in']}:{p['echo_out']}:{p['echo_delays']}:{echo_decays},"
        f"alimiter=limit={p['limit']}"
    )

    if style == "robot_v1":
        # Intensity scales robot layer mix (ringmod mix, chorus depths)
        ring_mix = min(1.0, ROBOT_V1_RINGMOD_MIX * i) if i > 0 else 0.0
        core += f",ringmod=f={ROBOT_V1_RINGMOD_FREQ}:mix={ring_mix}"
        core += f",chorus={ROBOT_V1_CHORUS}"

    if speed != 1.0:
        return _atempo_filter(speed) + "," + core
    return core


def apply_c3po_fx(
    raw_path: str | Path,
    out_path: str | Path,
    intensity: float | None = None,
    speed: float | None = None,
) -> str:
    """
    Apply C-3PO FX to raw TTS audio using ffmpeg. Output format follows out_path suffix (.mp3 or .wav).
    Uses argv list (shell=False). Raises FileNotFoundError or RuntimeError on failure.
    """
    raw_path = Path(raw_path)
    out_path = Path(out_path)

    from threepio.config.settings import get_settings

    settings = get_settings()
    if intensity is None:
        intensity = settings.C3PO_FX_INTENSITY
    if speed is None:
        ptts = (settings.PROVIDER_TTS or "").strip().lower()
        speed = settings.ELEVENLABS_SPEED if ptts == "elevenlabs" else 1.0

    filter_chain = build_c3po_fx_chain(intensity, speed)
    if _debug_enabled():
        print(f"[C3PO-FX] chain={filter_chain}", flush=True)
        if speed != 1.0:
            print(f"[C3PO-FX] speed={speed} speed_applied_via=ffmpeg_atempo", flush=True)
    logger.info("[C3PO-FX] chain=%s", filter_chain)

    # Atomic-ish write: same dir temp then rename (avoids partial files)
    out_path = Path(out_path)
    tmp_path = out_path.parent / (out_path.stem + ".tmp" + (out_path.suffix or ""))
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-af",
        filter_chain,
        "-vn",
    ]
    if out_path.suffix.lower() == ".mp3":
        cmd.extend(["-c:a", "libmp3lame"])
    cmd.append(str(tmp_path))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except FileNotFoundError:
        raise FileNotFoundError(
            "ffmpeg not found. Install with: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"
        ) from None

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "unknown").strip()
        lines = [ln for ln in err.split("\n") if ln.strip()]
        tail = lines[-20:] if len(lines) > 20 else lines
        tail_str = "\n".join(tail) if tail else "unknown"
        logger.debug("[C3PO-FX] ffmpeg stderr tail: %s", tail_str)
        raise RuntimeError(f"ffmpeg C3PO-FX failed: {tail_str}")

    tmp_path.replace(out_path)
    logger.debug("[C3PO-FX] wrote %s chain=%s", out_path, filter_chain)
    return filter_chain
