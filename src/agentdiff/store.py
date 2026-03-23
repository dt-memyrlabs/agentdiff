from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from agentdiff.models import ChangeRecord

AGENTDIFF_DIR = ".agentdiff"
SESSIONS_DIR = "sessions"
CHANGES_FILE = "changes.jsonl"


def _sanitize_session_id(session_id: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', session_id)


def get_session_dir(project_root: str, session_id: str) -> Path:
    safe_id = _sanitize_session_id(session_id)
    return Path(project_root) / AGENTDIFF_DIR / SESSIONS_DIR / safe_id


def _lock_write(fd: int, data: bytes) -> None:
    if os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            time.sleep(0.01)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                pass  # fail-open
        os.write(fd, data)
        try:
            os.fsync(fd)
        except OSError:
            pass
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            time.sleep(0.01)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                pass  # fail-open
        os.write(fd, data)
        try:
            os.fsync(fd)
        except OSError:
            pass
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


def append_change(project_root: str, session_id: str, record: ChangeRecord) -> None:
    session_dir = get_session_dir(project_root, session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / CHANGES_FILE
    data = (record.to_json_line() + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT)
    try:
        _lock_write(fd, data)
    finally:
        os.close(fd)


def read_changes(project_root: str, session_id: str) -> list[ChangeRecord]:
    path = get_session_dir(project_root, session_id) / CHANGES_FILE
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = ChangeRecord.from_json_line(line)
            if record is not None:
                records.append(record)
    return records


def read_all_changes(project_root: str) -> list[ChangeRecord]:
    sessions_dir = Path(project_root) / AGENTDIFF_DIR / SESSIONS_DIR
    if not sessions_dir.exists():
        return []
    records = []
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        changes_file = session_dir / CHANGES_FILE
        if not changes_file.exists():
            continue
        with open(changes_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = ChangeRecord.from_json_line(line)
                if record is not None:
                    records.append(record)
    records.sort(key=lambda r: r.timestamp)
    return records


def read_file_changes(project_root: str, file_path: str) -> list[ChangeRecord]:
    all_changes = read_all_changes(project_root)
    normalized = _normalize_path(file_path)
    return [r for r in all_changes if _normalize_path(r.file_path) == normalized]


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").strip("/")


def find_project_root(start: Path | None = None) -> str:
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / AGENTDIFF_DIR).is_dir():
            return str(parent)
    raise FileNotFoundError(
        f"No {AGENTDIFF_DIR}/ found. Run 'agentdiff init' in your project root."
    )


def ensure_agentdiff_dir(project_root: str) -> Path:
    agentdiff_dir = Path(project_root) / AGENTDIFF_DIR
    sessions_dir = agentdiff_dir / SESSIONS_DIR
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return agentdiff_dir
