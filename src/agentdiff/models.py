from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class ChangeRecord:
    schema_version: int
    change_id: str
    timestamp: str
    session_id: str
    tool_name: str
    file_path: str
    content: str | None = None
    old_string: str | None = None
    new_string: str | None = None
    prompt: str | None = None
    reasoning: str | None = None
    provenance: str = "agent"

    @staticmethod
    def create(
        session_id: str,
        tool_name: str,
        file_path: str,
        *,
        content: str | None = None,
        old_string: str | None = None,
        new_string: str | None = None,
        prompt: str | None = None,
        reasoning: str | None = None,
        provenance: str = "agent",
    ) -> ChangeRecord:
        return ChangeRecord(
            schema_version=1,
            change_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            tool_name=tool_name,
            file_path=file_path,
            content=content,
            old_string=old_string,
            new_string=new_string,
            prompt=prompt,
            reasoning=reasoning,
            provenance=provenance,
        )

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), default=str)

    @staticmethod
    def from_json_line(line: str) -> ChangeRecord | None:
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None
            if data.get("schema_version", 0) > 1:
                return None
            known_fields = {f.name for f in ChangeRecord.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in known_fields}
            for req in ("schema_version", "change_id", "timestamp", "session_id", "tool_name", "file_path"):
                if req not in filtered:
                    return None
            return ChangeRecord(**filtered)
        except (json.JSONDecodeError, TypeError):
            return None


@dataclass
class BlameLine:
    line_number: int
    content: str
    provenance: str = "unknown"
    change_id: str | None = None
    session_id: str | None = None
    prompt: str | None = None
    reasoning: str | None = None
    timestamp: str | None = None
