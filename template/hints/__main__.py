"""CLI for the hints system.

Usage:
    /hints              # show status
    /hints off          # disable all hints
    /hints on           # re-enable hints
    /hints status       # show current state
    /hints reset        # reset to defaults
    /hints dismiss ID   # dismiss a specific hint
"""
from __future__ import annotations

import sys
from pathlib import Path

from hints._state import ActivationConfig, HintStateStore

# Resolve project root (look for .claude/ directory going up)
_PROJECT_ROOT = Path.cwd()


def _store_and_activation() -> tuple[HintStateStore, ActivationConfig]:
    store = HintStateStore(_PROJECT_ROOT)
    return store, ActivationConfig(store)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    cmd = args[0] if args else "status"

    if cmd == "off":
        store, act = _store_and_activation()
        act.disable_globally()
        store.save()
        print("Hints disabled. Re-enable with: /hints on")

    elif cmd == "on":
        store, act = _store_and_activation()
        act.enable_globally()
        store.save()
        print("Hints enabled.")

    elif cmd == "status":
        _store, act = _store_and_activation()
        state = "enabled" if act.is_globally_enabled else "disabled"
        print(f"Hints: {state}")
        if act.disabled_hints:
            print(f"Dismissed: {', '.join(sorted(act.disabled_hints))}")
        print("State file: .claude/hints_state.json")

    elif cmd == "reset":
        p = _PROJECT_ROOT / ".claude" / "hints_state.json"
        if p.exists():
            p.unlink()
            print("Hints state reset to defaults.")
        else:
            print("No state file found — already at defaults.")

    elif cmd == "dismiss":
        if len(args) < 2:
            print("Usage: /hints dismiss <hint-id>")
            return
        hint_id = args[1]
        store, act = _store_and_activation()
        act.disable_hint(hint_id)
        store.save()
        print(f"Dismissed: {hint_id}")

    elif cmd == "help":
        print("Usage: /hints [command]")
        print("")
        print("Commands:")
        print("  status          Show current hints state (default)")
        print("  off             Disable all hints")
        print("  on              Re-enable hints")
        print("  dismiss <id>    Dismiss a specific hint")
        print("  reset           Reset to defaults")
        print("  help            Show this help")

    else:
        print(f"Unknown command: {cmd}")
        print("Run: /hints help")


if __name__ == "__main__":
    main()
