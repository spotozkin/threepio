"""Ambient mode: continuous listen, TTS response, barge-in (stop playback when user speaks)."""

from __future__ import annotations

import logging
from typing import Any
import os
import queue
import struct
import tempfile
import time
import uuid
from collections import deque
from pathlib import Path

from threepio.audio.mic_stream import (
    MicStream,
    _device_info_from_query,
    frame_rms_peak,
    resolve_audio_input_device,
    write_wav as write_wav_frames,
)
from threepio.audio.vad import (
    VAD_BYTES_PER_FRAME,
    VAD_FRAME_MS,
    VAD_SAMPLE_RATE,
    VADMonitor,
    count_speech_frames_combined,
    detect_speech_end,
    detect_speech_start,
    energy_bargein_confirmed,
    energy_speech_end,
    energy_speech_start,
    get_bargein_confirm_ms,
    get_post_speech_cooldown_ms,
    get_speech_suppress_ms,
    get_vad_cooldown_ms,
    get_vad_start_rms,
    is_speaking_suppression_active,
    should_accept_speech,
    vad_speech_start_allowed,
)
from threepio.speech.playback import NO_PLAYER_MESSAGE, PlaybackHandle, play_audio_file_interruptible

logger = logging.getLogger(__name__)


def _frame_min_max_int16(frame: bytes) -> tuple[int, int]:
    """Min and max int16 value in frame (from first 960 bytes)."""
    n = min(len(frame) // 2, VAD_BYTES_PER_FRAME // 2)
    if n < 1:
        return (0, 0)
    try:
        samples = struct.unpack(f"<{n}h", frame[: n * 2])
        return (min(samples), max(samples))
    except struct.error:
        return (0, 0)


SILENCE_MS_THRESHOLD = 700


def _debug_enabled() -> bool:
    v = os.environ.get("THREEPIO_DEBUG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _status(msg: str) -> None:
    print(f"[ambient] {msg}", flush=True)


def _load_user_profile_fns() -> tuple[Any, ...]:
    """
    Load user_profile helpers or return no-op fallbacks if the module is missing.
    Returns (get_preferred_address, load_profile, mark_addressed, save_profile, should_inject_address, update_from_user_text).
    """
    try:
        from threepio.memory.user_profile import (
            get_preferred_address,
            load_profile,
            mark_addressed,
            save_profile,
            should_inject_address,
            update_from_user_text,
        )
        return (
            get_preferred_address,
            load_profile,
            mark_addressed,
            save_profile,
            should_inject_address,
            update_from_user_text,
        )
    except ModuleNotFoundError as e:
        if "user_profile" in str(e):
            _status("memory disabled: threepio.memory.user_profile not found")
            logger.info("user_profile not found, using no-op fallbacks: %s", e)
        else:
            raise
        return (
            lambda p: None,
            lambda speaker_id="default", base_dir=".": {},
            lambda p, now: None,
            lambda p, base_dir=".": None,
            lambda p, now, cooldown_s=90.0: False,
            lambda profile, text: profile if profile is not None else {},
        )


def _load_classify_fn() -> Any:
    """
    Load persona governor classify or return a fallback if c3po_governor is missing.
    Fallback returns {"allow": True} so the pipeline continues with normal assistant replies.
    """
    try:
        from threepio.persona.c3po_governor import classify
        return classify
    except (ModuleNotFoundError, ImportError) as e:
        if "c3po_governor" in str(e):
            _status("persona governor disabled: threepio.persona.c3po_governor not found")
            logger.info("c3po_governor not found, using allow-all fallback: %s", e)
        else:
            raise

        def _classify_fallback(text: str) -> dict[str, Any]:
            return {"allow": True}

        return _classify_fallback


def _load_address_gating_fns() -> Any:
    """
    Load extract_speaker_address from address_gating or return a no-op fallback if the module is missing.
    Fallback returns None so the pipeline continues without speaker address extraction.
    """
    try:
        from threepio.persona.address_gating import extract_speaker_address
        return extract_speaker_address
    except ModuleNotFoundError as e:
        if "address_gating" in str(e):
            _status("address gating disabled: threepio.persona.address_gating not found")
            logger.info("address_gating not found, using no-op fallback: %s", e)
        else:
            raise

        def _extract_speaker_address_fallback(profile: Any, *args: Any, **kwargs: Any) -> None:
            return None

        return _extract_speaker_address_fallback


def _load_flavor_governor_fn() -> Any:
    """
    Load flavor_intent from flavor_governor or return a no-op fallback if the module is missing.
    Fallback returns None (no special flavor / default) so the pipeline continues.
    """
    try:
        from threepio.persona.flavor_governor import flavor_intent
        return flavor_intent
    except ModuleNotFoundError as e:
        if "flavor_governor" in str(e):
            _status("flavor governor disabled: threepio.persona.flavor_governor not found")
            logger.info("flavor_governor not found, using fallback: %s", e)
        else:
            raise

        def _flavor_intent_fallback(text: str, *args: Any, **kwargs: Any) -> None:
            return None

        return _flavor_intent_fallback


def _load_prompt_builder_fn() -> Any:
    """Load build_c3po_system_prompt or return fallback that gives a default prompt."""
    try:
        from threepio.persona.prompt_builder import build_c3po_system_prompt
        return build_c3po_system_prompt
    except (ModuleNotFoundError, ImportError) as e:
        if "prompt_builder" in str(e) or "persona" in str(e):
            _status("prompt_builder disabled: using default THREEPIO prompt")
            logger.info("prompt_builder not found: %s", e)
        else:
            raise

        def _prompt_fallback(profile: Any = None, *, mode: str = "ambient") -> str:
            return "You are THREEPIO, a helpful C-3PO-inspired assistant."

        return _prompt_fallback


def _load_slang_gloss_fn() -> Any:
    """Load slang_to_formal_gloss or return no-op (identity)."""
    try:
        from threepio.persona.reality_threepio import slang_to_formal_gloss
        return slang_to_formal_gloss
    except (ModuleNotFoundError, ImportError):
        return lambda text: ""


def _load_notes_fns() -> tuple[Any, Any, Any]:
    """Load add_note, extract_note_from_user_text, should_save_note or no-ops."""
    try:
        from threepio.memory.notes import add_note, extract_note_from_user_text, should_save_note
        return add_note, extract_note_from_user_text, should_save_note
    except (ModuleNotFoundError, ImportError):
        return (
            lambda title, content: None,
            lambda text: (None, None),
            lambda text: False,
        )


def _load_semantic_filter_fn() -> Any:
    """Load interpret_user_intent for slang-to-formal interpretation, or no-op."""
    try:
        from threepio.persona.semantic_filter import interpret_user_intent
        return interpret_user_intent
    except (ModuleNotFoundError, ImportError):
        return lambda text: ""


def transcribe_wav(path: Path, settings: Any) -> tuple[str, Any]:
    """
    Transcribe WAV file to text. Uses local faster-whisper with STT_* settings.
    Returns (text, info) where info has .language (detected or requested).
    Raises RuntimeError with instructions if STT is not available.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"WAV not found: {path}")
    model_size = getattr(settings, "STT_MODEL", "small")
    language = getattr(settings, "STT_LANGUAGE", "en")
    if language == "":
        language = None
    beam_size = getattr(settings, "STT_BEAM_SIZE", 5)
    try:
        from threepio.speech.stt.local_whisper import transcribe as local_whisper_transcribe
        text, info = local_whisper_transcribe(path, model_size=model_size, language=language, beam_size=beam_size)
        detected = getattr(info, "language", None)
        logger.debug(
            "[ambient] stt model=%s language=%s transcript=%s",
            model_size,
            detected or language,
            (text or "")[:80],
        )
        return (text.strip(), info)
    except ImportError as e:
        raise RuntimeError(
            "STT required for --ambient. Install faster-whisper:\n"
            "  pip install faster-whisper\n"
            "Then run again. The ambient loop is ready; only transcription was missing."
        ) from e
    except Exception as e:
        if "faster-whisper" in str(e).lower() or "faster_whisper" in str(e):
            raise RuntimeError(
                "STT required for --ambient. Install faster-whisper:\n"
                "  pip install faster-whisper\n"
                "Then run again."
            ) from e
        raise


def run_vad_test(device_in: int | None = None, duration_sec: float = 10.0) -> None:
    """
    Run mic capture for duration_sec and print rms/peak plus whether speech would be accepted
    (RMS gate only; no STT/LLM/TTS). Use to tune THREEPIO_VAD_START_RMS and related env vars.
    """
    import sounddevice as sd
    if device_in is None:
        resolved_device_index, _ = resolve_audio_input_device()
    elif isinstance(device_in, int):
        resolved_device_index = device_in
    else:
        resolved_device_index, _ = resolve_audio_input_device(str(device_in))
    if resolved_device_index is None:
        _status("No input device resolved; set THREEPIO_AUDIO_INPUT_DEVICE.")
        return
    resolved_device_index = int(resolved_device_index)
    mic = MicStream(device=resolved_device_index)
    try:
        mic.start()
    except Exception as e:
        _status(f"Mic failed: {e}")
        return
    _status(f"VAD test: {duration_sec}s capture on device {resolved_device_index}. Speak to see rms/would_accept.")
    start = time.time()
    preroll: list[bytes] = []
    recent_frames: list[bytes] = []
    rms_recent: deque[float] = deque(maxlen=50)
    frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
    log_interval = 0.3
    last_log_ts = 0.0
    start_rms = get_vad_start_rms()
    cooldown_ms = get_vad_cooldown_ms()
    try:
        while time.time() - start < duration_sec:
            try:
                frame = mic.read_frame()
            except Exception:
                break
            if frame is None or len(frame) != VAD_BYTES_PER_FRAME:
                continue
            rms, peak = frame_rms_peak(frame)
            rms_recent.append(rms)
            recent_frames.append(frame)
            if len(recent_frames) > 30:
                recent_frames.pop(0)
            vad_start = detect_speech_start(
                preroll + recent_frames, current_rms=rms, current_peak=peak, log_event=False
            )
            energy_start = energy_speech_start(rms_recent, n_frames=3)
            is_vad_speech = vad_start or energy_start
            now_ms = int(time.time() * 1000)
            would_accept = should_accept_speech(is_vad_speech, rms, now_ms, 0, start_rms, cooldown_ms)
            now = time.time()
            if now - last_log_ts >= log_interval:
                last_log_ts = now
                print(
                    f"[vad-test] rms={rms:.4f} peak={peak:.4f} vad={vad_start} energy={energy_start} "
                    f"would_accept={would_accept} (threshold={start_rms})",
                    flush=True,
                )
    finally:
        mic.stop()
    _status("VAD test done.")


def run(
    settings: Any,
    device_in: int | None = None,
    vad_threshold: float | None = None,
) -> int:
    """
    Single public entrypoint for ambient mode. Starts the state machine loop and blocks.
    Returns 0 if loop exits normally, 1 if startup failed or exited early.
    """
    _status("starting")
    mode = getattr(settings, "AUDIO_OUTPUT_MODE", "auto") or "auto"
    try:
        from threepio.speech.playback import get_playback_command_with_mode
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            probe_path = Path(f.name)
        try:
            probe_path.write_bytes(b"\x00" * 960)
            _, playback_name = get_playback_command_with_mode(probe_path, mode)
        finally:
            probe_path.unlink(missing_ok=True)
    except Exception:
        playback_name = mode
    _status(f"playback={playback_name}")

    silence_ms = int(vad_threshold) if vad_threshold is not None else SILENCE_MS_THRESHOLD
    run_ambient(mic_device=device_in, silence_ms=silence_ms)
    return 1


def run_ambient(
    *,
    mic_device: int | str | None = None,
    silence_ms: int = SILENCE_MS_THRESHOLD,
) -> None:
    """
    Run ambient loop: IDLE -> LISTENING -> THINKING -> SPEAKING.
    Barge-in: when user speaks during SPEAKING, stop playback and go to LISTENING.
    """
    from threepio.config.settings import get_settings
    from threepio.llm.provider import generate_reply, get_llm_client
    get_preferred_address, load_profile, mark_addressed, save_profile, should_inject_address, update_from_user_text = _load_user_profile_fns()
    # Classify from loader only (no direct c3po_governor import) so ambient runs if that module is missing
    classify = _load_classify_fn()
    extract_speaker_address = _load_address_gating_fns()
    flavor_intent = _load_flavor_governor_fn()
    build_c3po_system_prompt = _load_prompt_builder_fn()
    slang_to_formal_gloss = _load_slang_gloss_fn()
    interpret_user_intent = _load_semantic_filter_fn()
    add_note, extract_note_from_user_text, should_save_note = _load_notes_fns()
    from threepio.speech.echo_guard import apply_echo_guard
    from threepio.speech.text_shaping import shape_for_speech
    from threepio.speech.tts.provider import get_tts_provider, synthesize_to_file

    # State
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    state = IDLE

    settings = get_settings()
    tts = get_tts_provider()
    try:
        llm_client = get_llm_client()
    except Exception as e:
        _status(f"LLM unavailable: {e}. --ambient requires OPENAI_API_KEY and PROVIDER_LLM=openai.")
        return

    base_dir = Path(".").resolve()
    profile = load_profile("default", base_dir)
    messages: list[dict[str, str]] = []
    speaker_address: str | None = None
    system_prompt = None  # built per turn

    # Resolve input device: numeric string → int index; else substring match (input-capable only)
    import sounddevice as sd
    if mic_device is None:
        resolved_device_index, resolved_device_name = resolve_audio_input_device()
    elif isinstance(mic_device, int):
        resolved_device_index = mic_device
        resolved_device_name = str(mic_device)
    else:
        resolved_device_index, resolved_device_name = resolve_audio_input_device(str(mic_device))
    if resolved_device_index is None:
        _status("No input device resolved; set THREEPIO_AUDIO_INPUT_DEVICE (e.g. 1 or device name substring).")
        return
    resolved_device_index = int(resolved_device_index)
    name, max_input_channels, default_samplerate = _device_info_from_query(sd, resolved_device_index)
    _status(f"resolved input: index={resolved_device_index} name={name!r} (THREEPIO_AUDIO_INPUT_DEVICE or default)")
    mic = MicStream(device=resolved_device_index)
    try:
        mic.start()
    except Exception as e:
        _status(f"Mic failed: {e}")
        return

    _status("Listening. Speak to start; speak again during reply to barge-in.")
    # Min utterance: THREEPIO_MIN_UTTERANCE_SEC overrides settings.MIN_UTTERANCE_SEC
    _min_utterance_env = os.environ.get("THREEPIO_MIN_UTTERANCE_SEC", "").strip()
    min_utterance_sec = float(_min_utterance_env) if _min_utterance_env else getattr(settings, "MIN_UTTERANCE_SEC", 1.2)
    if _debug_enabled():
        print(f"[ambient] min_utterance_sec={min_utterance_sec}", flush=True)
        print("[ambient] state=IDLE", flush=True)

    listen_frames: list[bytes] = []
    max_listen_frames = 300  # ~9s cap
    debug_frame_count = 0
    silent_seconds = 0.0
    last_level_time = None
    silent_warning_printed = False
    vad_debug_window: deque[bytes] = deque(maxlen=30)
    vad_debug_rms: deque[float] = deque(maxlen=30)
    last_vad_debug_log_time: float | None = None
    silence_frames = max(1, silence_ms // VAD_FRAME_MS)
    rms_recent: deque[float] = deque(maxlen=max(silence_frames + 5, 50))
    cooldown_until_ts: float | None = None
    reject_cooldown_until_ts: float | None = None  # after "too short" or "no speech detected"
    last_reject_ts: float | None = None  # timestamp when we last rejected (for should_accept_speech)
    bargein_debounce_frames = 0  # after barge-in, discard this many frames before accumulating listen_frames

    frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
    raw_path: Path | None = None
    playback_path: Path | None = None
    state_ref: list[str] = [state]
    handle_ref: list[PlaybackHandle | None] = [None]
    ffmpeg_checked_ref: list[bool] = [False]
    ffmpeg_available_ref: list[bool] = [True]

    def _on_bargein_speech_start() -> None:
        if state_ref[0] != SPEAKING:
            return
        # THREEPIO_ENABLE_BARGE_IN (default true). When false, never interrupt playback.
        enable = os.environ.get("THREEPIO_ENABLE_BARGE_IN", os.environ.get("THREEPIO_BARGE_IN", "1")).strip().lower()
        if enable in ("0", "false", "no"):
            if _debug_enabled():
                print("[ambient] barge-in disabled (THREEPIO_ENABLE_BARGE_IN=false)", flush=True)
            return
        h = handle_ref[0]
        if h is not None and h.is_running():
            h.stop()
        handle_ref[0] = None
        state_ref[0] = LISTENING
        preroll = mic.get_preroll_frames()
        last_f = vad_monitor.get_last_frame()
        listen_frames.clear()
        listen_frames.extend(preroll)
        if last_f:
            listen_frames.append(last_f)
        nonlocal bargein_debounce_frames
        bargein_debounce_frames = int(
            os.environ.get("THREEPIO_BARGEIN_DEBOUNCE_FRAMES", "2")
        )
        print("[barge-in] accepted, stopping playback (via=VADMonitor)", flush=True)
        _status("Barge-in. Listening...")
        if _debug_enabled():
            print("[ambient] barge-in -> LISTENING", flush=True)

    def _on_speech_end_listening() -> None:
        # Main loop drives LISTENING->THINKING via detect_speech_end; no-op here to avoid duplicate
        pass

    vad_monitor = VADMonitor(
        read_frame=mic.read_frame,
        on_speech_start=_on_bargein_speech_start,
        on_speech_end=_on_speech_end_listening,
        silence_ms=silence_ms,
        frame_bytes=VAD_BYTES_PER_FRAME,
        mode="listening",
        frame_queue=frame_queue,
    )
    vad_monitor.start()

    try:
        while True:
            if state_ref[0] == SPEAKING:
                state = SPEAKING
                while handle_ref[0] is not None and handle_ref[0].is_running() and state_ref[0] == SPEAKING:
                    time.sleep(0.02)
                if state_ref[0] == SPEAKING:
                    state_ref[0] = IDLE
                    state = IDLE
                    vad_monitor.set_mode("listening")
                    vad_monitor.set_speaking_start_ts(None)
                    handle_ref[0] = None
                    _status("Idle.")
                    cooldown_until_ts = time.time() + (get_post_speech_cooldown_ms() / 1000.0)
                if raw_path is not None and raw_path.exists():
                    raw_path.unlink(missing_ok=True)

                if (
                    playback_path is not None
                    and raw_path is not None
                    and playback_path != raw_path
                    and playback_path.exists()
                ):
                    playback_path.unlink(missing_ok=True)

                raw_path = None
                playback_path = None
                continue

            try:
                frame = frame_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            state = state_ref[0]
            preroll = mic.get_preroll_frames()

            rms, peak = frame_rms_peak(frame)
            rms_recent.append(rms)
            # VAD uses raw int16 bytes; meter uses same frame but does not modify it
            frame_ok_for_vad = len(frame) == VAD_BYTES_PER_FRAME
            dtype = mic.get_last_indata_dtype()
            if dtype is not None:
                try:
                    import numpy as np
                    frame_ok_for_vad = frame_ok_for_vad and (getattr(dtype, "name", None) == "int16" or dtype == np.int16)
                except ImportError:
                    pass

            if _debug_enabled():
                debug_frame_count += 1
                vad_debug_window.append(frame)
                vad_debug_rms.append(rms)
                # Once per second: indata dtype, min/max int16, len(frame_bytes), sample_rate
                now = time.time()
                if last_vad_debug_log_time is None or (now - last_vad_debug_log_time) >= 1.0:
                    last_vad_debug_log_time = now
                    min_val, max_val = _frame_min_max_int16(frame)
                    dtype_str = str(dtype) if dtype is not None else "None"
                    print(
                        f"[ambient] vad_debug indata_dtype={dtype_str} "
                        f"min={min_val} max={max_val} len(frame_bytes)={len(frame)} "
                        f"sample_rate={VAD_SAMPLE_RATE}",
                        flush=True,
                    )
                    if not frame_ok_for_vad:
                        print(
                            "[ambient] WARNING: skip VAD this frame (dtype != int16 or len != %d)" % VAD_BYTES_PER_FRAME,
                            flush=True,
                        )
                # ~1 second: level meter
                if debug_frame_count % 34 == 0:
                    print(f"[ambient] level rms={rms:.4f} peak={peak:.4f}", flush=True)
                # Every ~30 frames: speech frame count (webrtcvad OR energy)
                if debug_frame_count % 30 == 0 and len(vad_debug_window) == 30 and len(vad_debug_rms) == 30:
                    speech_count = count_speech_frames_combined(vad_debug_window, vad_debug_rms)
                    print(f"[ambient] vad= speech_frames={speech_count}/30", flush=True)
                if rms < 0.001 and peak < 0.001:
                    if last_level_time is None:
                        last_level_time = time.time()
                    else:
                        silent_seconds = time.time() - last_level_time
                        if silent_seconds > 2.0 and not silent_warning_printed:
                            print(
                                "[ambient] Mic audio appears silent; check device selection/permissions.",
                                flush=True,
                            )
                            silent_warning_printed = True
                else:
                    last_level_time = None
                    silent_seconds = 0.0
                    silent_warning_printed = False

            if state == IDLE:
                vad_start = frame_ok_for_vad and detect_speech_start(
                    preroll + [frame], current_rms=rms, current_peak=peak, log_event=False
                )
                energy_start = energy_speech_start(rms_recent, n_frames=3)
                is_vad_speech = vad_start or energy_start
                vad_start_rms = get_vad_start_rms()
                cooldown_ms = get_vad_cooldown_ms()
                now_ts = time.time()
                now_ms = int(now_ts * 1000)
                last_reject_ms = int(last_reject_ts * 1000) if last_reject_ts is not None else 0
                speech_start = should_accept_speech(
                    is_vad_speech, rms, now_ms, last_reject_ms, vad_start_rms, cooldown_ms
                )
                if is_vad_speech and not speech_start:
                    # Rejected: log one line when THREEPIO_DEBUG=1
                    if _debug_enabled():
                        reason = "low_rms" if rms < vad_start_rms else "cooldown"
                        cooldown_remaining_ms = (
                            max(0, int((reject_cooldown_until_ts - now_ts) * 1000))
                            if reject_cooldown_until_ts is not None and now_ts < reject_cooldown_until_ts
                            else 0
                        )
                        print(
                            f"[ambient] speech_start rejected reason={reason} rms={rms:.4f} threshold={vad_start_rms} "
                            f"cooldown_remaining_ms={cooldown_remaining_ms} device_index={resolved_device_index} sample_rate={VAD_SAMPLE_RATE}",
                            flush=True,
                        )
                    continue
                if speech_start:
                    if cooldown_until_ts is not None and now_ts < cooldown_until_ts:
                        print("[ambient] trigger ignored (post-speech cooldown)", flush=True)
                    else:
                        cooldown_until_ts = None
                        state = LISTENING
                        state_ref[0] = LISTENING
                        listen_frames = list(preroll) + [frame]
                        _status("Listening...")
                        via = "webrtcvad" if vad_start else "energy"
                        print(f"[VAD] speech_start via={via} rms={rms:.4f}", flush=True)
                        if _debug_enabled():
                            print(
                                f"[ambient] speech_start accepted rms={rms:.4f} threshold={vad_start_rms} "
                                f"device_index={resolved_device_index} sample_rate={VAD_SAMPLE_RATE}",
                                flush=True,
                            )
                            print("[ambient] state=LISTENING (VAD speech start)", flush=True)

            elif state == LISTENING:
                if bargein_debounce_frames > 0:
                    bargein_debounce_frames -= 1
                    continue
                if not listen_frames:
                    listen_frames = list(preroll) + [frame]
                else:
                    listen_frames.append(frame)
                if len(listen_frames) > max_listen_frames:
                    listen_frames = listen_frames[-max_listen_frames:]
                vad_end = frame_ok_for_vad and detect_speech_end(
                    listen_frames, silence_ms_threshold=silence_ms, current_rms=rms, current_peak=peak, log_event=False
                )
                energy_end_detected = energy_speech_end(rms_recent, silence_frames)
                speech_end = vad_end or energy_end_detected
                if speech_end:
                    duration_sec = len(listen_frames) * (VAD_FRAME_MS / 1000.0)
                    if duration_sec < min_utterance_sec:
                        if _debug_enabled():
                            print(f"[ambient] utterance too short: {duration_sec:.2f}s < {min_utterance_sec}s, not finalizing", flush=True)
                        last_reject_ts = time.time()
                        reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                        continue
                    state = THINKING
                    state_ref[0] = THINKING
                    _status("Thinking...")
                    via = "webrtcvad" if vad_end else "energy"
                    print(f"[VAD] speech_end via={via} rms={rms:.4f}", flush=True)
                    if _debug_enabled():
                        print("[ambient] state=THINKING (VAD speech end)", flush=True)
                    wav_path = Path(tempfile.gettempdir()) / f"ambient_{uuid.uuid4().hex[:12]}.wav"
                    try:
                        write_wav_frames(wav_path, listen_frames)
                    except Exception as e:
                        logger.exception("write_wav failed")
                        _status(f"Record save failed: {e}")
                        state = IDLE
                        state_ref[0] = IDLE
                        listen_frames = []
                        continue
                    try:
                        user_text, _stt_info = transcribe_wav(wav_path, settings)
                    except RuntimeError as e:
                        _status(str(e))
                        state = IDLE
                        state_ref[0] = IDLE
                        listen_frames = []
                        wav_path.unlink(missing_ok=True)
                        continue
                    if not user_text:
                        _status("No speech detected.")
                        state = IDLE
                        state_ref[0] = IDLE
                        listen_frames = []
                        last_reject_ts = time.time()
                        reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                        wav_path.unlink(missing_ok=True)
                        continue
                    # Voice ID only after STT: require real speech and minimum duration
                    duration_sec = len(listen_frames) * (VAD_FRAME_MS / 1000.0)
                    min_voice_sec = float(os.environ.get("THREEPIO_VOICE_MIN_SEC", "0.9"))
                    speaker_identity: str | None = None
                    if duration_sec >= min_voice_sec:
                        try:
                            from threepio.identity.voice_id import (
                                compute_embedding,
                                load_voiceprints,
                                match_speaker,
                            )
                            embedding = compute_embedding(wav_path)
                            voiceprints = load_voiceprints()
                            best_name, best_score, top = match_speaker(embedding, voiceprints, top_k=2)
                            if best_name:
                                speaker_identity = best_name
                            if _debug_enabled():
                                for n, s in top[:2]:
                                    print(f"[ambient] voice_id top: {n!r} score={s:.4f}", flush=True)
                                print(f"[ambient] voice_id applied={speaker_identity!r} duration_sec={duration_sec:.2f}", flush=True)
                        except Exception as e:
                            logger.debug("voice_id: %s", e)
                    elif _debug_enabled():
                        print(f"[ambient] voice_id skipped duration_sec={duration_sec:.2f} (min={min_voice_sec}) or no speech", flush=True)
                    wav_path.unlink(missing_ok=True)
                    print(f"You: {user_text}", flush=True)
                    listen_frames = []

                    # Build system and get reply (only final reply to TTS)
                    state_obj = classify(user_text)
                    profile = update_from_user_text(profile, user_text)
                    if speaker_identity:
                        if hasattr(profile, "model_copy"):
                            profile = profile.model_copy(update={"name": speaker_identity})
                        else:
                            profile = {**profile, "name": speaker_identity}
                    save_profile(profile, base_dir)
                    if should_save_note(user_text):
                        pair = extract_note_from_user_text(user_text)
                        if pair and pair[0] is not None and pair[1] is not None:
                            add_note(pair[0], pair[1])
                    addr = extract_speaker_address(profile)
                    if addr is not None:
                        speaker_address = addr
                    is_first = len(messages) == 0
                    sys_content = build_c3po_system_prompt(profile, mode="ambient", user_text=user_text)
                    now_ts = time.time()
                    if get_preferred_address(profile) and should_inject_address(profile, now_ts, cooldown_s=90.0):
                        mark_addressed(profile, now_ts)
                        save_profile(profile, base_dir)
                    formal_intent = interpret_user_intent(user_text)
                    gloss = slang_to_formal_gloss(user_text)
                    if formal_intent:
                        user_content = (
                            f"User intent (formal interpretation; do not repeat slang): {formal_intent}\n\n"
                            f"User said: {user_text}"
                        )
                    elif gloss:
                        user_content = (
                            f"User slang gloss: {gloss} (do not reveal gloss unless asked)\n\n"
                            f"User: {user_text}"
                        )
                    else:
                        user_content = user_text
                    if not messages or messages[0].get("role") != "system":
                        messages.insert(0, {"role": "system", "content": sys_content})
                    else:
                        messages[0] = {"role": "system", "content": sys_content}
                    messages.append({"role": "user", "content": user_content})
                    _deflect = (
                        getattr(state_obj, "name", None) == "DEFLECT"
                        or (isinstance(state_obj, dict) and not state_obj.get("allow", True))
                    )
                    if _deflect:
                        reply = "I am afraid I must remain in character as C-3PO."
                    else:
                        try:
                            reply = generate_reply(messages, client=llm_client)
                        except Exception as e:
                            _status(f"LLM failed: {e}")
                            messages.pop()
                            state = IDLE
                            state_ref[0] = IDLE
                            continue
                    if _debug_enabled():
                        print("[LLM] requests_this_turn=1", flush=True)
                    messages.append({"role": "assistant", "content": reply})
                    # Keep system + last 10 user/assistant pairs
                    max_turns = 10
                    while len(messages) > 1 + max_turns * 2:
                        # Drop oldest user or assistant message (keep system at 0)
                        if len(messages) > 1:
                            messages.pop(1)
                    cleaned = apply_echo_guard(user_text, reply)
                    display_text, speech_text = shape_for_speech(cleaned)
                    print(f"C-3PO: {display_text}", flush=True)

                    # Synthesize and apply FX (same pipeline as main, no echo)
                    out_dir = Path("data/tts")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    ext = ".mp3"
                    raw_path = out_dir / f"ambient_{uuid.uuid4().hex[:12]}{ext}"
                    try:
                        synthesize_to_file(tts, speech_text, str(raw_path))
                    except Exception as e:
                        _status(f"TTS failed: {e}")
                        state = IDLE
                        state_ref[0] = IDLE
                        continue
                    playback_path = raw_path
                    enable_fx = getattr(settings, "ENABLE_C3PO_FX", False)
                    if not enable_fx:
                        logger.debug("[fx] skipped (reason=disabled)")
                    else:
                        if not ffmpeg_checked_ref[0]:
                            import shutil
                            ffmpeg_checked_ref[0] = True
                            ffmpeg_available_ref[0] = bool(shutil.which("ffmpeg"))
                            if not ffmpeg_available_ref[0]:
                                _status("ffmpeg not found. Install: brew install ffmpeg (macOS) or apt install ffmpeg (Linux). Set ENABLE_C3PO_FX=false to skip.")
                        if not ffmpeg_available_ref[0]:
                            logger.debug("[fx] skipped (reason=missing_ffmpeg)")
                        else:
                            logger.debug("[fx] applying")
                            from threepio.speech.tts.c3po_fx import apply_c3po_fx
                            processed = out_dir / f"ambient_fx_{uuid.uuid4().hex[:12]}.wav"
                            try:
                                apply_c3po_fx(str(raw_path), str(processed))
                                playback_path = processed
                            except Exception as e:
                                logger.warning("[fx] skipped (reason=missing_fx_chain or error): %s", e)
                    state = SPEAKING
                    state_ref[0] = SPEAKING
                    _status("Speaking...")
                    if _debug_enabled():
                        print("[ambient] state=SPEAKING", flush=True)
                    # Suppression at exact moment playback starts: no barge-in / VAD finalization for THREEPIO_SPEECH_SUPPRESS_MS
                    vad_monitor.set_mode("barge_in")
                    suppress_ms = get_speech_suppress_ms()
                    vad_monitor.set_speaking_start_ts(time.time())
                    _status(f"speaking suppression active for {suppress_ms} ms")
                    handle = play_audio_file_interruptible(playback_path)
                    if handle is None:
                        _status(NO_PLAYER_MESSAGE)
                        state = IDLE
                        state_ref[0] = IDLE
                        continue
                    handle_ref[0] = handle
                    continue

    except KeyboardInterrupt:
        _status("Stopping.")
    finally:
        mic.stop()
