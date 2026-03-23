"""Hook handler for Claude Code events.

Invoked as a short-lived process per hook event. Reads JSON from stdin,
routes by event type, writes to JSONL, exits 0 always (fail-open).

Usage in Claude Code settings.json:
  {
    "hooks": {
      "PostToolUse": [{
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": "python path/to/hook_handler.py", "timeout": 5}]
      }]
    }
  }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _extract_prompt_from_transcript(transcript_path: str | None) -> str | None:
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-50:] if len(lines) > 50 else lines
        for line in reversed(tail):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("role") == "human" or entry.get("type") == "human":
                content = entry.get("message", entry.get("content", ""))
                if isinstance(content, list):
                    texts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    return " ".join(texts).strip() or None
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return None
    except Exception:
        return None


def _extract_reasoning_from_transcript(transcript_path: str | None) -> str | None:
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-80:] if len(lines) > 80 else lines
        for line in reversed(tail):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("role") == "assistant" or entry.get("type") == "assistant":
                content = entry.get("message", entry.get("content", ""))
                if isinstance(content, list):
                    texts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    text = " ".join(texts).strip()
                    if text:
                        return text[:500]
                if isinstance(content, str) and content.strip():
                    return content.strip()[:500]
        return None
    except Exception:
        return None


def _make_relative(file_path: str, cwd: str) -> str:
    try:
        return str(Path(file_path).resolve().relative_to(Path(cwd).resolve()))
    except (ValueError, OSError):
        return file_path.replace("\\", "/")


def handle_post_tool_use(event: dict, cwd: str, session_id: str) -> None:
    from agentdiff.models import ChangeRecord
    from agentdiff.store import append_change, ensure_agentdiff_dir

    tool_name = event.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return

    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    rel_path = _make_relative(file_path, cwd)
    transcript_path = event.get("transcript_path")
    prompt = _extract_prompt_from_transcript(transcript_path)
    reasoning = _extract_reasoning_from_transcript(transcript_path)

    ensure_agentdiff_dir(cwd)

    record = ChangeRecord.create(
        session_id=session_id,
        tool_name=tool_name,
        file_path=rel_path,
        content=tool_input.get("content"),
        old_string=tool_input.get("old_string"),
        new_string=tool_input.get("new_string"),
        prompt=prompt,
        reasoning=reasoning,
        provenance="agent",
    )
    append_change(cwd, session_id, record)


def handle_stop(event: dict, cwd: str, session_id: str) -> None:
    from agentdiff.models import ChangeRecord
    from agentdiff.store import append_change, get_session_dir

    session_dir = get_session_dir(cwd, session_id)
    if not session_dir.exists():
        return

    record = ChangeRecord.create(
        session_id=session_id,
        tool_name="_session_end",
        file_path="",
        provenance="system",
    )
    append_change(cwd, session_id, record)


def main() -> None:
    try:
        # Ensure package is importable when run as standalone script
        _src_dir = str(Path(__file__).resolve().parent.parent)
        if _src_dir not in sys.path:
            sys.path.insert(0, _src_dir)

        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        event = json.loads(raw)
        event_name = event.get("hook_event_name", "")
        cwd = event.get("cwd", str(Path.cwd()))
        session_id = event.get("session_id", "unknown")

        if event_name == "PostToolUse":
            handle_post_tool_use(event, cwd, session_id)
        elif event_name == "Stop":
            handle_stop(event, cwd, session_id)
    except Exception:
        pass  # fail-open: never block Claude Code
    sys.exit(0)


if __name__ == "__main__":
    main()
