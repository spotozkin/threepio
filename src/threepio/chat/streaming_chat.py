"""Low-latency typed chat loop with streaming output, sentence-chunked TTS, and barge-in.

Usage: python -m threepio.chat.streaming_chat

Commands: /quit, /mode fast|long, /memory, /reset
"""

from __future__ import annotations

import logging
import queue
import re
import sys
import threading
import time

from threepio.brain.respond import QUIT_SIGNAL, Responder
from threepio.chat.cancel import CancelScope
from threepio.chat.conversation import ConversationManager
from threepio.config import get_settings
from threepio.core.events import EventBus
from threepio.core.logging_subscriber import create_logging_subscriber
from threepio.core.state import DroidEvent
from threepio.core.state_machine import StateMachine
from threepio.speech.tts import get_tts_provider
from threepio.tools.router import ToolRouter

logger = logging.getLogger(__name__)

# Fast mode system instruction (used when LLM supports it; Responder is already short)
FAST_MODE_SYSTEM_INSTRUCTION = (
    "Reply in 1–2 sentences unless the user explicitly asks for detail."
)

# Sentence boundary: . ! ? followed by whitespace or end
SENTENCE_END_RE = re.compile(r"(?<=[.!?])(?:\s+|$)")
STREAM_CHUNK_SIZE = 35  # chars per chunk for simulated streaming (25–50 range)


def _iter_sentences(text: str):
    """Yield complete sentences. Trailing text without punctuation yielded at end."""
    if not text or not text.strip():
        return
    parts = SENTENCE_END_RE.split(text)
    for p in parts:
        s = p.strip()
        if s:
            yield s


def _simulate_stream_chunks(text: str, chunk_size: int = STREAM_CHUNK_SIZE):
    """Simulate streaming: yield text in small chunks. No extra deps, stdlib only."""
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


def _is_quit(text: str) -> bool:
    return text.strip().lower() in ("quit", "/quit")


def _parse_command(line: str) -> tuple[str | None, str]:
    """Parse /command. Returns (command, rest) or (None, line)."""
    s = line.strip()
    if not s.startswith("/"):
        return None, line
    parts = s[1:].split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    rest = (parts[1] if len(parts) > 1 else "").strip()
    return cmd, rest


def _get_response(
    responder: Responder,
    tts,
    user_text: str,
    fast_mode: bool,
) -> str:
    """Get assistant response. Reuses app.py logic."""
    if _is_quit(user_text):
        return QUIT_SIGNAL
    if hasattr(tts, "get_reply"):
        return tts.get_reply(user_text)
    # Responder is sync; fast_mode hint reserved for future LLM integration
    _ = fast_mode  # noqa: F841
    return responder.respond(user_text)


def _run_input_thread(
    input_queue: queue.Queue[str],
    cancel_scope: CancelScope,
) -> None:
    """Read from stdin, cancel previous scope on new input, enqueue message."""
    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            cancel_scope.cancel()
            input_queue.put("/quit")
            return
        cancel_scope.cancel()
        input_queue.put(line)


def run_streaming_loop() -> None:
    """Run streaming chat loop with sentence-by-sentence TTS and barge-in."""
    settings = get_settings()
    max_turns = getattr(settings, "CHAT_MAX_TURNS", 40)
    summary_every = getattr(settings, "CHAT_SUMMARY_EVERY", 8)
    persona = getattr(settings, "CHAT_PERSONA", "") or ""
    fast_mode = (getattr(settings, "CHAT_MODE", "fast") == "fast")
    conv = ConversationManager(
        max_turns=max_turns,
        summary_every=summary_every,
        persona=persona,
        fast_mode=fast_mode,
    )
    tool_router = ToolRouter()
    responder = Responder(memory=conv, tool_router=tool_router)
    tts = get_tts_provider()

    input_queue: queue.Queue[str] = queue.Queue()
    cancel_scope = CancelScope()

    bus = EventBus()
    bus.subscribe(create_logging_subscriber())
    StateMachine(bus)

    print("Streaming chat mode. Type and press Enter. /quit to exit.")

    input_thread = threading.Thread(
        target=_run_input_thread,
        args=(input_queue, cancel_scope),
        daemon=True,
    )
    input_thread.start()

    while True:
        try:
            user_text = input_queue.get()
        except KeyboardInterrupt:
            break

        if _is_quit(user_text):
            print("Goodbye!")
            break

        cmd, rest = _parse_command(user_text)
        if cmd == "mode":
            if rest in ("fast", "long"):
                fast_mode = rest == "fast"
                conv.set_fast_mode(fast_mode)
                print(f"Mode set to: {'fast' if fast_mode else 'long'}")
            else:
                print("Usage: /mode fast|long")
            continue
        if cmd == "memory":
            summary = conv.summary
            print(f"Summary: {summary or '(empty)'}")
            continue
        if cmd == "reset":
            conv.reset()
            print("Memory cleared.")
            continue
        if cmd:
            print(f"Unknown command: /{cmd}")
            continue

        cancel_scope.reset()
        bus.emit(DroidEvent(type="user_input_finalized", payload={"text": user_text[:50]}))

        bus.emit(DroidEvent(type="llm_started", payload={}))
        response = _get_response(responder, tts, user_text, fast_mode)
        bus.emit(DroidEvent(type="llm_finished", payload={}))
        if response == QUIT_SIGNAL:
            print("Goodbye!")
            break

        conv.add_user(user_text)

        print("Threepio: ", end="", flush=True)
        interrupted = False

        # Simulate streaming: accumulate chunks, speak when sentence boundary found
        buffer = ""
        for chunk in _simulate_stream_chunks(response):
            if cancel_scope.is_cancelled:
                bus.emit(DroidEvent(type="barge_in", payload={}))
                tts.stop_playback()
                interrupted = True
                break
            buffer += chunk
            print(chunk, end="", flush=True)
            # Extract complete sentences from buffer
            while True:
                m = SENTENCE_END_RE.search(buffer)
                if not m:
                    break
                end = m.end()
                sentence = buffer[:end].strip()
                buffer = buffer[end:].lstrip()
                if not sentence:
                    continue
                if cancel_scope.is_cancelled:
                    bus.emit(DroidEvent(type="barge_in", payload={}))
                    tts.stop_playback()
                    interrupted = True
                    break
                bus.emit(DroidEvent(type="tts_started", payload={}))
                done = threading.Event()
                speak_error: list[Exception] = []

                def speak_task(s: str = sentence) -> None:
                    try:
                        tts.speak(s)
                    except Exception as e:
                        speak_error.append(e)
                    finally:
                        done.set()

                t = threading.Thread(target=speak_task, daemon=True)
                t.start()
                while not done.is_set() and not cancel_scope.is_cancelled:
                    time.sleep(0.05)
                if cancel_scope.is_cancelled:
                    bus.emit(DroidEvent(type="barge_in", payload={}))
                    tts.stop_playback()
                    t.join(timeout=2)
                    interrupted = True
                    break
                t.join()
                if speak_error:
                    bus.emit(DroidEvent(type="error", payload={"message": str(speak_error[0])}))
                    print(f"\n[TTS error: {speak_error[0]}]", file=sys.stderr)
            if interrupted:
                break

        # Speak any remainder
        if not interrupted and buffer.strip():
            sentence = buffer.strip()
            if cancel_scope.is_cancelled:
                bus.emit(DroidEvent(type="barge_in", payload={}))
                tts.stop_playback()
                interrupted = True
            else:
                bus.emit(DroidEvent(type="tts_started", payload={}))
                done = threading.Event()
                speak_error_list: list[Exception] = []

                def speak_remainder(s: str = sentence) -> None:
                    try:
                        tts.speak(s)
                    except Exception as e:
                        speak_error_list.append(e)
                    finally:
                        done.set()

                t = threading.Thread(target=speak_remainder, daemon=True)
                t.start()
                while not done.is_set() and not cancel_scope.is_cancelled:
                    time.sleep(0.05)
                if cancel_scope.is_cancelled:
                    bus.emit(DroidEvent(type="barge_in", payload={}))
                    tts.stop_playback()
                    t.join(timeout=2)
                    interrupted = True
                else:
                    t.join()
                    if speak_error_list:
                        bus.emit(DroidEvent(type="error", payload={"message": str(speak_error_list[0])}))
                        print(f"\n[TTS error: {speak_error_list[0]}]", file=sys.stderr)
                    bus.emit(DroidEvent(type="tts_finished", payload={"all_done": True}))
        elif not interrupted:
            bus.emit(DroidEvent(type="tts_finished", payload={"all_done": True}))

        if not interrupted:
            print()
            conv.add_assistant(response)
            conv.maybe_summarize()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_streaming_loop()


if __name__ == "__main__":
    main()
