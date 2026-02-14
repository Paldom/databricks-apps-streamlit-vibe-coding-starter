# Local Hooks

These hooks provide lightweight quality checks inspired by `everything-claude-code` without requiring plugin installation.

Configured hooks:
- `pre-bash-reminders.py` (PreToolUse/Bash): reminders before risky or long-lived commands.
- `post-edit-python-check.py` (PostToolUse/Edit|Write): Python syntax check + `print()` reminder.

Hook wiring lives in `.claude/settings.json`.
