"""Entry point for `python -m threepio`."""

from threepio.config.env_loader import _maybe_load_dotenv

_maybe_load_dotenv()

from threepio.main import main

if __name__ == "__main__":
    main()
