# Hook Guidelines

- Prefer warning-style hooks over blocking hooks for day-to-day development.
- Keep hooks fast, deterministic, and local-tool-only.
- Always pass the original hook payload through to stdout.
- Use hooks to catch obvious regressions early (syntax errors, risky commands, secret leakage hints).
