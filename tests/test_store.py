import json
from pathlib import Path

from agentdiff.models import ChangeRecord
from agentdiff.store import (
    append_change,
    read_all_changes,
    read_changes,
    read_file_changes,
    find_project_root,
    ensure_agentdiff_dir,
)


def test_append_and_read(project_dir):
    record = ChangeRecord.create(
        session_id="sess-1",
        tool_name="Write",
        file_path="main.py",
        content="print('hi')",
    )
    append_change(str(project_dir), "sess-1", record)

    changes = read_changes(str(project_dir), "sess-1")
    assert len(changes) == 1
    assert changes[0].file_path == "main.py"
    assert changes[0].content == "print('hi')"


def test_multiple_records(project_dir):
    for i in range(5):
        record = ChangeRecord.create(
            session_id="sess-1",
            tool_name="Write",
            file_path=f"file{i}.py",
            content=f"# file {i}",
        )
        append_change(str(project_dir), "sess-1", record)

    changes = read_changes(str(project_dir), "sess-1")
    assert len(changes) == 5


def test_multiple_sessions(project_dir):
    for sid in ("sess-a", "sess-b"):
        record = ChangeRecord.create(
            session_id=sid,
            tool_name="Write",
            file_path="shared.py",
            content=f"# {sid}",
        )
        append_change(str(project_dir), sid, record)

    all_changes = read_all_changes(str(project_dir))
    assert len(all_changes) == 2


def test_read_file_changes(project_dir):
    for f in ("a.py", "b.py", "a.py"):
        record = ChangeRecord.create(
            session_id="sess-1",
            tool_name="Write",
            file_path=f,
            content=f"# {f}",
        )
        append_change(str(project_dir), "sess-1", record)

    a_changes = read_file_changes(str(project_dir), "a.py")
    assert len(a_changes) == 2
    b_changes = read_file_changes(str(project_dir), "b.py")
    assert len(b_changes) == 1


def test_corrupt_line_skipped(project_dir):
    record = ChangeRecord.create(
        session_id="sess-1",
        tool_name="Write",
        file_path="test.py",
        content="ok",
    )
    append_change(str(project_dir), "sess-1", record)

    # Append corrupt line
    changes_file = project_dir / ".agentdiff" / "sessions" / "sess-1" / "changes.jsonl"
    with open(changes_file, "a") as f:
        f.write("THIS IS NOT JSON\n")

    # Append another valid record
    record2 = ChangeRecord.create(
        session_id="sess-1",
        tool_name="Edit",
        file_path="test.py",
        old_string="ok",
        new_string="good",
    )
    append_change(str(project_dir), "sess-1", record2)

    changes = read_changes(str(project_dir), "sess-1")
    assert len(changes) == 2  # corrupt line skipped


def test_find_project_root(project_dir):
    # Create nested directory
    nested = project_dir / "src" / "deep"
    nested.mkdir(parents=True)

    root = find_project_root(nested)
    assert root == str(project_dir)


def test_find_project_root_not_found(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        find_project_root(tmp_path)


def test_ensure_agentdiff_dir(tmp_path):
    result = ensure_agentdiff_dir(str(tmp_path))
    assert (tmp_path / ".agentdiff" / "sessions").is_dir()


def test_session_id_sanitized(project_dir):
    record = ChangeRecord.create(
        session_id="bad/../session",
        tool_name="Write",
        file_path="test.py",
    )
    append_change(str(project_dir), "bad/../session", record)
    # Should not create path traversal
    assert not (project_dir / ".agentdiff" / "sessions" / "bad" / ".." / "session").exists()
    changes = read_changes(str(project_dir), "bad/../session")
    assert len(changes) == 1
