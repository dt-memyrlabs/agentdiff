"""Three-pass blame engine for AI-generated code.

Pass 1: Replay Write operations via difflib to track line attribution.
Pass 2: Apply Edit operations to override attribution on affected lines.
Pass 3: Detect human changes via git diff.
"""
from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

from agentdiff.models import BlameLine, ChangeRecord
from agentdiff.store import read_file_changes


def blame_file(project_root: str, file_path: str) -> list[BlameLine]:
    """Attribute each line of a file to its origin (agent, human, or unknown)."""
    abs_path = Path(project_root) / file_path
    if not abs_path.exists():
        return []

    current_lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not current_lines:
        return []

    changes = read_file_changes(project_root, file_path)
    if not changes:
        return [
            BlameLine(line_number=i + 1, content=line, provenance="unknown")
            for i, line in enumerate(current_lines)
        ]

    # Initialize attribution: None means unattributed
    attribution: list[ChangeRecord | None] = [None] * len(current_lines)

    # Pass 1: Replay Write operations
    writes = [c for c in changes if c.tool_name == "Write" and c.content is not None]
    _replay_writes(writes, current_lines, attribution)

    # Pass 2: Apply Edit operations
    edits = [c for c in changes if c.tool_name == "Edit" and c.new_string is not None]
    _apply_edits(edits, current_lines, attribution)

    # Pass 3: Detect human changes via git diff
    human_lines = _detect_human_changes(project_root, file_path)

    # Build BlameLine output
    result = []
    for i, line in enumerate(current_lines):
        record = attribution[i]
        if i + 1 in human_lines and record is None:
            provenance = "human"
            result.append(BlameLine(
                line_number=i + 1,
                content=line,
                provenance=provenance,
            ))
        elif record is not None:
            result.append(BlameLine(
                line_number=i + 1,
                content=line,
                provenance="agent",
                change_id=record.change_id,
                session_id=record.session_id,
                prompt=record.prompt,
                reasoning=record.reasoning,
                timestamp=record.timestamp,
            ))
        else:
            result.append(BlameLine(
                line_number=i + 1,
                content=line,
                provenance="unknown",
            ))
    return result


def _replay_writes(
    writes: list[ChangeRecord],
    current_lines: list[str],
    attribution: list[ChangeRecord | None],
) -> None:
    """Pass 1: Diff consecutive Write snapshots to track line attribution."""
    if not writes:
        return

    # Build snapshot chain
    snapshots: list[tuple[list[str], ChangeRecord]] = []
    for w in writes:
        lines = (w.content or "").splitlines()
        snapshots.append((lines, w))

    # First write: all lines attributed to it
    prev_lines, prev_record = snapshots[0]
    prev_attr: list[ChangeRecord | None] = [prev_record] * len(prev_lines)

    # Diff consecutive snapshots
    for snap_lines, snap_record in snapshots[1:]:
        new_attr: list[ChangeRecord | None] = [None] * len(snap_lines)
        matcher = difflib.SequenceMatcher(None, prev_lines, snap_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for offset in range(j2 - j1):
                    new_attr[j1 + offset] = prev_attr[i1 + offset] if (i1 + offset) < len(prev_attr) else snap_record
            elif tag in ("replace", "insert"):
                for j in range(j1, j2):
                    new_attr[j] = snap_record
            # 'delete': lines removed, no attribution needed
        prev_lines = snap_lines
        prev_attr = new_attr

    # Map last snapshot attribution to current file lines
    matcher = difflib.SequenceMatcher(None, prev_lines, current_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(j2 - j1):
                src_idx = i1 + offset
                if src_idx < len(prev_attr) and prev_attr[src_idx] is not None:
                    attribution[j1 + offset] = prev_attr[src_idx]
        elif tag in ("replace", "insert"):
            # Lines changed since last write — leave unattributed for Pass 3
            pass


def _apply_edits(
    edits: list[ChangeRecord],
    current_lines: list[str],
    attribution: list[ChangeRecord | None],
) -> None:
    """Pass 2: Find Edit new_string content in current file, override attribution."""
    for edit in edits:
        new_string = edit.new_string
        if not new_string:
            continue
        match_lines = new_string.splitlines()
        if not match_lines:
            continue

        indices = _find_block_in_lines(current_lines, match_lines)
        if indices:
            for idx in indices:
                if 0 <= idx < len(attribution):
                    attribution[idx] = edit


def _find_block_in_lines(
    file_lines: list[str], block_lines: list[str]
) -> list[int] | None:
    """Find a contiguous block of lines in a file. Returns line indices or None."""
    if not block_lines:
        return None
    block_len = len(block_lines)
    for start in range(len(file_lines) - block_len + 1):
        if file_lines[start : start + block_len] == block_lines:
            return list(range(start, start + block_len))

    # Fallback: stripped comparison
    stripped_block = [l.strip() for l in block_lines]
    for start in range(len(file_lines) - block_len + 1):
        stripped_file = [l.strip() for l in file_lines[start : start + block_len]]
        if stripped_file == stripped_block:
            return list(range(start, start + block_len))

    return None


_HUNK_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _detect_human_changes(project_root: str, file_path: str) -> set[int]:
    """Pass 3: Use git diff to find lines modified by humans."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--unified=0", "--", file_path],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return set()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return set()

    human_lines: set[int] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("@@"):
            continue
        match = _HUNK_RE.search(line)
        if match:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1
            for i in range(start, start + count):
                human_lines.add(i)
    return human_lines
