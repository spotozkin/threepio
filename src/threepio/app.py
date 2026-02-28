"""Application orchestrator with state machine and tool loop."""

import logging
import sys
from typing import NoReturn

from threepio.brain.respond import QUIT_SIGNAL, Responder
from threepio.config import get_settings
from threepio.eyes.controller import EyesController
from threepio.input.events import EventType
from threepio.input.providers import ConsoleInputProvider
from threepio.memory.memory import ConversationMemory
from threepio.runtime.lifecycle import LifecycleManager
from threepio.runtime.state import SystemState
from threepio.runtime.log import setup_runtime_logging
from threepio.tools.router import ToolRouter

logger = logging.getLogger(__name__)


def run_main_loop() -> None:
    """Run main conversation loop with state machine."""
    settings = get_settings()

    lifecycle = LifecycleManager()
    eyes = EyesController()
    lifecycle.register_cleanup(eyes.shutdown)

    memory = ConversationMemory(max_turns=min(settings.MEMORY_TURNS, 12))
    tool_router = ToolRouter()
    responder = Responder(memory=memory, tool_router=tool_router)
    input_provider = ConsoleInputProvider()

    lifecycle.set_state(SystemState.BOOTING)
    eyes.start()
    lifecycle.set_state(SystemState.IDLE)

    print("THREEPIO ready. Type your message and press Enter. Type 'quit' to exit.\n")

    try:
        while True:
            lifecycle.set_state(SystemState.LISTENING)
            event = input_provider.get_event_blocking()

            if event.type != EventType.TEXT:
                continue
            text = event.payload.get("text", "").strip()
            if not text:
                lifecycle.set_state(SystemState.IDLE)
                continue

            lifecycle.set_state(SystemState.THINKING)
            response = responder.respond(text)

            if response == QUIT_SIGNAL:
                logger.info("User requested quit")
                break

            lifecycle.set_state(SystemState.SPEAKING)
            print(f"THREEPIO: {response}")
            memory.add_user(text)
            memory.add_assistant(response)
            lifecycle.set_state(SystemState.IDLE)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        lifecycle.run_cleanup()
        print("\nGoodbye!")


def _validate_openai_key(api_key: str | None) -> None:
    """Raise if OPENAI_API_KEY is missing or invalid (required for Realtime API)."""
    if not api_key or not str(api_key).strip():
        raise RuntimeError("OPENAI_API_KEY not set")
    if not str(api_key).strip().startswith("sk-"):
        raise RuntimeError(
            "OPENAI_API_KEY appears invalid (must start with sk-). "
            "Set OPENAI_API_KEY in .env or export it."
        )


def _should_run_realtime() -> bool:
    """True if realtime voice provider is configured and available. Raises if realtime requested but key missing."""
    settings = get_settings()
    if settings.PROVIDER_VOICE != "realtime":
        return False
    # Explicit check: no silent fallback when realtime requested without key
    if not (settings.OPENAI_API_KEY and str(settings.OPENAI_API_KEY).strip()):
        raise RuntimeError("OPENAI_API_KEY not set")
    _validate_openai_key(settings.OPENAI_API_KEY)
    logger.info("[ENV] OPENAI_API_KEY loaded")
    try:
        import websockets  # noqa: F401
        return True
    except ImportError:
        logger.warning(
            "PROVIDER_VOICE=realtime but websockets not installed. "
            "Run: pip install -e '.[realtime]'. Falling back to CLI mode."
        )
        return False


def main() -> NoReturn:
    """Entry point."""
    settings = get_settings()
    setup_runtime_logging(level=settings.LOG_LEVEL)
    if _should_run_realtime():
        from threepio.app_voice import run
        run()
    else:
        run_main_loop()
    sys.exit(0)
