from pathlib import Path

from agentdiff.blame import blame_file
from agentdiff.models import ChangeRecord
from agentdiff.store import append_change


def _write_file(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_single_write(project_dir):
    """A single Write attributes all lines to the agent."""
    content = "line1\nline2\nline3\n"
    _write_file(project_dir, "test.py", content)

    record = ChangeRecord.create(
        session_id="s1",
        tool_name="Write",
        file_path="test.py",
        content=content,
        prompt="Create test file",
    )
    append_change(str(project_dir), "s1", record)

    lines = blame_file(str(project_dir), "test.py")
    assert len(lines) == 3
    assert all(l.provenance == "agent" for l in lines)
    assert all(l.session_id == "s1" for l in lines)
    assert all(l.prompt == "Create test file" for l in lines)


def test_consecutive_writes(project_dir):
    """Two Writes — unchanged lines keep first attribution, new lines get second."""
    content_v1 = "line1\nline2\nline3\n"
    record1 = ChangeRecord.create(
        session_id="s1",
        tool_name="Write",
        file_path="test.py",
        content=content_v1,
        prompt="First write",
    )
    append_change(str(project_dir), "s1", record1)

    content_v2 = "line1\nMODIFIED\nline3\nnew_line4\n"
    _write_file(project_dir, "test.py", content_v2)

    record2 = ChangeRecord.create(
        session_id="s1",
        tool_name="Write",
        file_path="test.py",
        content=content_v2,
        prompt="Second write",
    )
    append_change(str(project_dir), "s1", record2)

    lines = blame_file(str(project_dir), "test.py")
    assert len(lines) == 4

    # line1 unchanged — should keep first attribution
    assert lines[0].prompt == "First write"
    # MODIFIED — new in second write
    assert lines[1].prompt == "Second write"
    # line3 unchanged — should keep first attribution
    assert lines[2].prompt == "First write"
    # new_line4 — new in second write
    assert lines[3].prompt == "Second write"


def test_edit_overrides_attribution(project_dir):
    """An Edit overrides attribution for the affected lines."""
    content = "def hello():\n    print('hello')\n    return True\n"
    _write_file(project_dir, "test.py", content)

    write_record = ChangeRecord.create(
        session_id="s1",
        tool_name="Write",
        file_path="test.py",
        content=content,
        prompt="Initial write",
    )
    append_change(str(project_dir), "s1", write_record)

    # Now edit changes print line
    new_content = "def hello():\n    print('world')\n    return True\n"
    _write_file(project_dir, "test.py", new_content)

    edit_record = ChangeRecord.create(
        session_id="s1",
        tool_name="Edit",
        file_path="test.py",
        old_string="    print('hello')",
        new_string="    print('world')",
        prompt="Fix greeting",
    )
    append_change(str(project_dir), "s1", edit_record)

    lines = blame_file(str(project_dir), "test.py")
    assert len(lines) == 3
    assert lines[0].prompt == "Initial write"  # def hello unchanged
    assert lines[1].prompt == "Fix greeting"   # edit overrides
    assert lines[2].prompt == "Initial write"  # return True unchanged


def test_no_changes_all_unknown(project_dir):
    """A file with no tracked changes shows all lines as unknown."""
    _write_file(project_dir, "mystery.py", "x = 1\ny = 2\n")

    lines = blame_file(str(project_dir), "mystery.py")
    assert len(lines) == 2
    assert all(l.provenance == "unknown" for l in lines)


def test_nonexistent_file(project_dir):
    """Blaming a nonexistent file returns empty list."""
    lines = blame_file(str(project_dir), "nope.py")
    assert lines == []


def test_empty_file(project_dir):
    """Blaming an empty file returns empty list."""
    _write_file(project_dir, "empty.py", "")
    lines = blame_file(str(project_dir), "empty.py")
    assert lines == []


def test_human_detection_via_git(git_project_dir):
    """Lines modified after the last Write are detected as human via git diff."""
    import subprocess

    content_v1 = "line1\nline2\nline3\n"
    _write_file(git_project_dir, "test.py", content_v1)

    # Commit the original
    subprocess.run(["git", "add", "test.py"], cwd=git_project_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=git_project_dir, capture_output=True)

    # Track the write
    record = ChangeRecord.create(
        session_id="s1",
        tool_name="Write",
        file_path="test.py",
        content=content_v1,
        prompt="Agent wrote this",
    )
    append_change(str(git_project_dir), "s1", record)

    # Human modifies line2
    content_v2 = "line1\nhuman_edit\nline3\n"
    _write_file(git_project_dir, "test.py", content_v2)

    lines = blame_file(str(git_project_dir), "test.py")
    assert len(lines) == 3
    assert lines[0].provenance == "agent"
    assert lines[1].provenance == "human"  # git diff detects this
    assert lines[2].provenance == "agent"


def test_multiple_sessions(project_dir):
    """Changes from different sessions are correctly attributed."""
    content_v1 = "# session 1\n"
    _write_file(project_dir, "shared.py", content_v1)
    append_change(str(project_dir), "s1", ChangeRecord.create(
        session_id="s1", tool_name="Write", file_path="shared.py",
        content=content_v1, prompt="Session 1 work",
    ))

    content_v2 = "# session 1\n# session 2\n"
    _write_file(project_dir, "shared.py", content_v2)
    append_change(str(project_dir), "s2", ChangeRecord.create(
        session_id="s2", tool_name="Write", file_path="shared.py",
        content=content_v2, prompt="Session 2 work",
    ))

    lines = blame_file(str(project_dir), "shared.py")
    assert len(lines) == 2
    assert lines[0].session_id == "s1"
    assert lines[1].session_id == "s2"
