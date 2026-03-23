# AgentDiff

Git blame for AI-generated code. Windows-native, daemonless.

Hooks into Claude Code and tracks every file change with prompt, reasoning, and session context. Then lets you ask: *who wrote this line, and why?*

## Architecture

No daemon. Each Claude Code hook event spawns a short-lived Python process that appends to a JSONL change log. Sub-millisecond overhead, zero process management.

```
Claude Code fires PostToolUse event
  → Python process starts
  → Reads JSON from stdin
  → Appends ChangeRecord to .agentdiff/sessions/<id>/changes.jsonl
  → Exits
```

Three-pass blame engine:
1. **Replay Writes** — diff consecutive file snapshots via difflib to track line attribution
2. **Apply Edits** — override attribution for lines modified by Edit operations
3. **Detect human changes** — use `git diff HEAD` to find lines modified outside Claude Code

## Install

```bash
cd path/to/agentdiff
uv venv && uv pip install -e .
```

## Usage

```bash
# Initialize in any project
cd your-project
agentdiff init       # creates .agentdiff/, registers hooks in .claude/settings.local.json

# Use Claude Code normally — all Write/Edit operations are captured

# View change history
agentdiff log
agentdiff log --file src/main.py --last 10

# See who wrote each line
agentdiff blame src/main.py
agentdiff blame src/main.py --json

# Health check
agentdiff doctor
```

## What it tracks

Every `Write` and `Edit` tool invocation captures:
- File path and content changes
- Session ID and timestamp
- User prompt that triggered the change (extracted from transcript)
- Agent reasoning (extracted from transcript)
- Schema version for forward compatibility

## Storage

Append-only JSONL files in `.agentdiff/sessions/<session_id>/changes.jsonl`. No database required. Human-readable, portable.

File locking uses `msvcrt` on Windows, `fcntl` on Unix. Fail-open — a lock failure never blocks Claude Code.

## Requirements

- Python >= 3.12
- Git (for human change detection)
- Claude Code

## Tests

```bash
uv run pytest tests/ -v
```
