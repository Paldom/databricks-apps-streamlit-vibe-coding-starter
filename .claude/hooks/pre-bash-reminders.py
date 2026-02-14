#!/usr/bin/env python3
"""PreToolUse reminders for Bash commands."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        sys.stdout.write(raw)
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")

    if "git push" in command:
        sys.stderr.write("[Hook] Reminder: review changes before pushing.\n")

    if "streamlit run" in command and not os.getenv("TMUX"):
        sys.stderr.write(
            "[Hook] Consider running long-lived Streamlit commands in tmux for stable logs.\n"
        )

    sys.stdout.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
