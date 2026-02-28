"""CLI to re-run first-run profile prompt and overwrite .threepio/profile.json."""

from __future__ import annotations

import sys
from pathlib import Path

from threepio.memory.user_profile import (
    get_profile_path,
    load_profile_file,
    prompt_profile,
    save_profile_file,
)


def main() -> int:
    """Interactive prompt for user profile; save to .threepio/profile.json."""
    base_dir = Path(".").resolve()
    existing = load_profile_file(base_dir)
    if existing:
        print(f"Current profile at {get_profile_path(base_dir)}", flush=True)
        print(f"  display_name={existing.display_name!r} address_style={existing.address_style} pronouns={existing.pronouns!r}", flush=True)
        print("Overwriting with new answers below.", flush=True)
    profile = prompt_profile()
    save_profile_file(profile, base_dir)
    print(f"Saved to {get_profile_path(base_dir)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
