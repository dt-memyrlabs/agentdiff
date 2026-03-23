import json
import subprocess
import sys
from pathlib import Path

from agentdiff.store import read_changes, ensure_agentdiff_dir


def test_post_tool_use_write(project_dir):
    """Hook handler processes a Write event and creates a JSONL record."""
    ensure_agentdiff_dir(str(project_dir))

    event = {
        "hook_event_name": "PostToolUse",
        "session_id": "test-sess",
        "cwd": str(project_dir),
        "transcript_path": "",
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(project_dir / "hello.py"),
            "content": "print('hello')\n",
        },
    }

    handler = Path(__file__).parent.parent / "src" / "agentdiff" / "hook_handler.py"
    result = subprocess.run(
        [sys.executable, str(handler)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(handler.parent.parent)},
    )

    assert result.returncode == 0

    changes = read_changes(str(project_dir), "test-sess")
    assert len(changes) == 1
    assert changes[0].tool_name == "Write"
    assert changes[0].content == "print('hello')\n"


def test_post_tool_use_edit(project_dir):
    """Hook handler processes an Edit event."""
    ensure_agentdiff_dir(str(project_dir))

    event = {
        "hook_event_name": "PostToolUse",
        "session_id": "test-sess",
        "cwd": str(project_dir),
        "transcript_path": "",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(project_dir / "hello.py"),
            "old_string": "hello",
            "new_string": "world",
        },
    }

    handler = Path(__file__).parent.parent / "src" / "agentdiff" / "hook_handler.py"
    result = subprocess.run(
        [sys.executable, str(handler)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(handler.parent.parent)},
    )

    assert result.returncode == 0

    changes = read_changes(str(project_dir), "test-sess")
    assert len(changes) == 1
    assert changes[0].tool_name == "Edit"
    assert changes[0].old_string == "hello"
    assert changes[0].new_string == "world"


def test_ignored_tool(project_dir):
    """Hook handler ignores non-Write/Edit tools."""
    ensure_agentdiff_dir(str(project_dir))

    event = {
        "hook_event_name": "PostToolUse",
        "session_id": "test-sess",
        "cwd": str(project_dir),
        "tool_name": "Read",
        "tool_input": {"file_path": "/some/file"},
    }

    handler = Path(__file__).parent.parent / "src" / "agentdiff" / "hook_handler.py"
    result = subprocess.run(
        [sys.executable, str(handler)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(handler.parent.parent)},
    )

    assert result.returncode == 0
    changes = read_changes(str(project_dir), "test-sess")
    assert len(changes) == 0


def test_malformed_input(project_dir):
    """Hook handler exits 0 on garbage input (fail-open)."""
    handler = Path(__file__).parent.parent / "src" / "agentdiff" / "hook_handler.py"
    result = subprocess.run(
        [sys.executable, str(handler)],
        input="THIS IS NOT JSON",
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(handler.parent.parent)},
    )
    assert result.returncode == 0


def test_empty_input():
    """Hook handler exits 0 on empty stdin."""
    handler = Path(__file__).parent.parent / "src" / "agentdiff" / "hook_handler.py"
    result = subprocess.run(
        [sys.executable, str(handler)],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(handler.parent.parent)},
    )
    assert result.returncode == 0


def test_stop_event(project_dir):
    """Hook handler processes Stop event and writes session end marker."""
    ensure_agentdiff_dir(str(project_dir))

    # First create a change so the session dir exists
    from agentdiff.models import ChangeRecord
    from agentdiff.store import append_change
    record = ChangeRecord.create(
        session_id="test-sess",
        tool_name="Write",
        file_path="test.py",
        content="x=1",
    )
    append_change(str(project_dir), "test-sess", record)

    event = {
        "hook_event_name": "Stop",
        "session_id": "test-sess",
        "cwd": str(project_dir),
        "transcript_path": "",
    }

    handler = Path(__file__).parent.parent / "src" / "agentdiff" / "hook_handler.py"
    result = subprocess.run(
        [sys.executable, str(handler)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        env={**__import__("os").environ, "PYTHONPATH": str(handler.parent.parent)},
    )

    assert result.returncode == 0
    changes = read_changes(str(project_dir), "test-sess")
    assert len(changes) == 2
    assert changes[-1].tool_name == "_session_end"
