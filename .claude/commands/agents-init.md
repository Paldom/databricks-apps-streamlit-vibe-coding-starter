---
description: "Regenerate AGENTS.md + CLAUDE.md wrapper, plus tag-driven skills/MCP/subagents"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
---

# /agents-init

Regenerate or update the AI-ready configuration for this repository using `agents-init`.

## What This Does

This command will:

1. **Analyze** your repository structure, dependencies, and configuration
2. **Detect** applicable tags (languages, frameworks, tools, platforms)
3. **Generate/Update** AGENTS.md with project-specific guidance
4. **Update** CLAUDE.md to reference AGENTS.md
5. **Configure** MCP servers based on detected technologies
6. **Install** relevant subagents in `.claude/agents/`

## Usage

### One-Shot (Analyze + Apply)

```bash
npx -y agents-init@latest
```

### Preview Changes (Dry Run)

```bash
npx -y agents-init@latest --dry-run
```

### Non-Interactive Mode (CI/CD)

```bash
npx -y agents-init@latest --no-interactive
```

## Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without writing anything |
| `--no-interactive` | Non-interactive mode (for CI/CD) |
| `--no-claude` | Skip Claude-powered generation, use templates only |
| `--no-agents-md` | Skip AGENTS.md generation |
| `--no-skills` | Skip skills installation |
| `--no-mcp` | Skip MCP configuration |
| `--no-subagents` | Skip subagent installation |
| `--force` | Overwrite existing files |
| `--verbose` | Show detailed output |

## Notes

- Existing files are backed up before modification (unless `--force` is used)
- Skills telemetry is disabled by default
- Review third-party MCP servers before enabling them
- Run this command whenever you want to update your AI configuration

---

*Powered by [agents-init](https://github.com/Paldom/agents-init)*
