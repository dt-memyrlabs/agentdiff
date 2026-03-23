import json
from agentdiff.models import ChangeRecord, BlameLine


def test_create_change_record():
    record = ChangeRecord.create(
        session_id="sess-1",
        tool_name="Write",
        file_path="src/main.py",
        content="print('hello')",
        prompt="Write hello world",
    )
    assert record.schema_version == 1
    assert record.session_id == "sess-1"
    assert record.tool_name == "Write"
    assert record.file_path == "src/main.py"
    assert record.content == "print('hello')"
    assert record.provenance == "agent"
    assert record.change_id  # not empty
    assert record.timestamp  # not empty


def test_to_json_line():
    record = ChangeRecord.create(
        session_id="sess-1",
        tool_name="Edit",
        file_path="src/main.py",
        old_string="foo",
        new_string="bar",
    )
    line = record.to_json_line()
    parsed = json.loads(line)
    assert parsed["tool_name"] == "Edit"
    assert parsed["old_string"] == "foo"
    assert parsed["new_string"] == "bar"


def test_from_json_line_valid():
    record = ChangeRecord.create(
        session_id="sess-1",
        tool_name="Write",
        file_path="test.py",
        content="x = 1",
    )
    line = record.to_json_line()
    restored = ChangeRecord.from_json_line(line)
    assert restored is not None
    assert restored.session_id == "sess-1"
    assert restored.content == "x = 1"


def test_from_json_line_corrupt():
    assert ChangeRecord.from_json_line("not json") is None
    assert ChangeRecord.from_json_line("{}") is None
    assert ChangeRecord.from_json_line("[]") is None


def test_from_json_line_future_schema():
    data = {
        "schema_version": 99,
        "change_id": "x",
        "timestamp": "t",
        "session_id": "s",
        "tool_name": "Write",
        "file_path": "f",
    }
    assert ChangeRecord.from_json_line(json.dumps(data)) is None


def test_from_json_line_ignores_unknown_fields():
    record = ChangeRecord.create(
        session_id="s",
        tool_name="Write",
        file_path="f.py",
    )
    data = json.loads(record.to_json_line())
    data["future_field"] = "whatever"
    restored = ChangeRecord.from_json_line(json.dumps(data))
    assert restored is not None
    assert restored.session_id == "s"


def test_blame_line_defaults():
    bl = BlameLine(line_number=1, content="hello")
    assert bl.provenance == "unknown"
    assert bl.change_id is None
