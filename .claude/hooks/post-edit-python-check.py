#!/usr/bin/env python3
"""PostToolUse checks for edited Python files."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

PRINT_PATTERN = re.compile(r"(?m)^\s*print\(")


def main() -> int:
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        sys.stdout.write(raw)
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path.endswith(".py"):
        sys.stdout.write(raw)
        return 0

    if not os.path.exists(file_path):
        sys.stdout.write(raw)
        return 0

    compile_check = subprocess.run(
        [sys.executable, "-m", "py_compile", file_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if compile_check.returncode != 0:
        sys.stderr.write(f"[Hook] Python syntax check failed: {file_path}\n")
        if compile_check.stderr:
            sys.stderr.write(compile_check.stderr.strip() + "\n")

    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        sys.stdout.write(raw)
        return 0

    if PRINT_PATTERN.search(content):
        sys.stderr.write(
            f"[Hook] `print()` detected in {file_path}. Prefer logging or Streamlit status APIs.\n"
        )

    sys.stdout.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
