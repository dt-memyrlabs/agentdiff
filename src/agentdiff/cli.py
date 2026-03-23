"""CLI for AgentDiff — git blame for AI-generated code."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

HOOK_HANDLER_PATH = str(
    (Path(__file__).parent / "hook_handler.py").resolve()
).replace("\\", "\\\\")


def _enable_ansi_windows() -> None:
    if os.name == "nt":
        os.system("")


@click.group()
def cli() -> None:
    """AgentDiff — git blame for AI-generated code."""
    pass


@cli.command()
@click.option("--project", default=".", help="Project root directory.")
def init(project: str) -> None:
    """Initialize AgentDiff in the current project."""
    from agentdiff.store import ensure_agentdiff_dir

    project_root = Path(project).resolve()
    if not project_root.is_dir():
        click.echo(f"Error: {project_root} is not a directory.", err=True)
        sys.exit(1)

    # Create .agentdiff/
    ensure_agentdiff_dir(str(project_root))
    click.echo(f"Created .agentdiff/ in {project_root}")

    # Update .gitignore
    _update_gitignore(project_root)

    # Register hooks
    _register_hooks(project_root)

    click.echo("AgentDiff initialized. Changes will be tracked in future Claude Code sessions.")


def _update_gitignore(project_root: Path) -> None:
    gitignore = project_root / ".gitignore"
    entry = ".agentdiff/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry in content:
            return
        if not content.endswith("\n"):
            content += "\n"
        content += f"{entry}\n"
        gitignore.write_text(content, encoding="utf-8")
    else:
        gitignore.write_text(f"{entry}\n", encoding="utf-8")
    click.echo("Added .agentdiff/ to .gitignore")


def _register_hooks(project_root: Path) -> None:
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_file = claude_dir / "settings.local.json"

    settings: dict = {}
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            settings = {}

    handler_path = str((Path(__file__).parent / "hook_handler.py").resolve())
    src_dir = str((Path(__file__).parent.parent).resolve())
    command = f'PYTHONPATH="{src_dir}" python "{handler_path}"'

    hooks = settings.setdefault("hooks", {})

    # PostToolUse hook for Write|Edit
    post_tool_hooks = hooks.setdefault("PostToolUse", [])
    if not _hook_already_registered(post_tool_hooks, "agentdiff"):
        post_tool_hooks.append({
            "matcher": "Write|Edit",
            "hooks": [{
                "type": "command",
                "command": command,
                "timeout": 5,
            }],
        })

    # Stop hook for session finalization
    stop_hooks = hooks.setdefault("Stop", [])
    if not _hook_already_registered(stop_hooks, "agentdiff"):
        stop_hooks.append({
            "hooks": [{
                "type": "command",
                "command": command,
                "timeout": 10,
            }],
        })

    settings_file.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    click.echo(f"Registered hooks in {settings_file}")


def _hook_already_registered(hook_list: list, marker: str) -> bool:
    for entry in hook_list:
        hooks = entry.get("hooks", [])
        for h in hooks:
            cmd = h.get("command", "")
            if "hook_handler.py" in cmd:
                return True
    return False


@cli.command()
@click.argument("file_path")
@click.option("--json-output", "json_out", is_flag=True, help="Output as JSON.")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors.")
def blame(file_path: str, json_out: bool, no_color: bool) -> None:
    """Show who wrote each line of a file and why."""
    from agentdiff.blame import blame_file
    from agentdiff.store import find_project_root

    try:
        project_root = find_project_root()
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    lines = blame_file(project_root, file_path)
    if not lines:
        click.echo(f"No data for {file_path}", err=True)
        sys.exit(1)

    if json_out:
        from dataclasses import asdict
        click.echo(json.dumps([asdict(l) for l in lines], indent=2))
        return

    use_color = not no_color and sys.stdout.isatty()
    if use_color:
        _enable_ansi_windows()

    for bl in lines:
        line_num = f"{bl.line_number:>4}"
        prov = f"{bl.provenance:>8}"
        session = (bl.session_id or "")[:8]
        prompt_short = (bl.prompt or "")[:60].replace("\n", " ")

        if use_color:
            if bl.provenance == "agent":
                prov_colored = f"\033[34m{prov}\033[0m"
                session_colored = f"\033[36m{session:<8}\033[0m"
            elif bl.provenance == "human":
                prov_colored = f"\033[32m{prov}\033[0m"
                session_colored = f"{'':8}"
                prompt_short = ""
            else:
                prov_colored = f"\033[90m{prov}\033[0m"
                session_colored = f"{'':8}"
                prompt_short = ""
            click.echo(
                f"{line_num} | {prov_colored} | {session_colored} | {bl.content}"
            )
        else:
            click.echo(
                f"{line_num} | {prov} | {session:<8} | {bl.content}"
            )
        if prompt_short and use_color:
            click.echo(f"{'':4}   {'':8}   {'':8}   \033[90m# {prompt_short}\033[0m")


@cli.command()
@click.option("--session", "session_id", default=None, help="Filter by session ID.")
@click.option("--file", "file_filter", default=None, help="Filter by file path.")
@click.option("--last", "last_n", default=None, type=int, help="Show last N changes.")
def log(session_id: str | None, file_filter: str | None, last_n: int | None) -> None:
    """Show change history."""
    from agentdiff.store import find_project_root, read_all_changes

    try:
        project_root = find_project_root()
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    changes = read_all_changes(project_root)

    # Filter out system markers
    changes = [c for c in changes if not c.tool_name.startswith("_")]

    if session_id:
        changes = [c for c in changes if c.session_id.startswith(session_id)]
    if file_filter:
        norm = file_filter.replace("\\", "/")
        changes = [c for c in changes if norm in c.file_path.replace("\\", "/")]

    changes.reverse()  # Most recent first
    if last_n:
        changes = changes[:last_n]

    if not changes:
        click.echo("No changes found.", err=True)
        return

    use_color = sys.stdout.isatty()
    if use_color:
        _enable_ansi_windows()

    for c in changes:
        ts = c.timestamp[:19].replace("T", " ")
        session = c.session_id[:8]
        tool = c.tool_name[:5]
        prompt = (c.prompt or "")[:50].replace("\n", " ")

        if use_color:
            click.echo(
                f"\033[90m{ts}\033[0m | "
                f"\033[36m{session:<8}\033[0m | "
                f"\033[33m{tool:>5}\033[0m | "
                f"{c.file_path} | "
                f"\033[90m{prompt}\033[0m"
            )
        else:
            click.echo(
                f"{ts} | {session:<8} | {tool:>5} | {c.file_path} | {prompt}"
            )


@cli.command()
def doctor() -> None:
    """Check AgentDiff health."""
    import shutil
    import subprocess

    _enable_ansi_windows()
    all_ok = True

    # Check .agentdiff/ exists
    try:
        from agentdiff.store import find_project_root
        project_root = find_project_root()
        _check_pass(".agentdiff/ directory found")
    except FileNotFoundError:
        _check_fail(".agentdiff/ directory not found — run 'agentdiff init'")
        all_ok = False
        project_root = None

    # Check git
    if shutil.which("git"):
        _check_pass("git available")
    else:
        _check_fail("git not found on PATH")
        all_ok = False

    # Check python
    if shutil.which("python"):
        _check_pass("python available")
    else:
        _check_fail("python not found on PATH")
        all_ok = False

    # Check hooks registered
    if project_root:
        settings_file = Path(project_root) / ".claude" / "settings.local.json"
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
                hooks = settings.get("hooks", {})
                if hooks.get("PostToolUse") and hooks.get("Stop"):
                    _check_pass("Hooks registered in settings.local.json")
                else:
                    _check_fail("Hooks missing — run 'agentdiff init'")
                    all_ok = False
            except (json.JSONDecodeError, OSError):
                _check_fail("Could not read settings.local.json")
                all_ok = False
        else:
            _check_fail("No .claude/settings.local.json — run 'agentdiff init'")
            all_ok = False

    # Check hook handler exists
    handler = Path(__file__).parent / "hook_handler.py"
    if handler.exists():
        _check_pass(f"Hook handler at {handler}")
    else:
        _check_fail(f"Hook handler missing at {handler}")
        all_ok = False

    # Check sessions
    if project_root:
        from agentdiff.store import read_all_changes
        changes = read_all_changes(project_root)
        if changes:
            _check_pass(f"{len(changes)} changes tracked across sessions")
        else:
            _check_info("No changes tracked yet — start a Claude Code session")

    if all_ok:
        click.echo("\nAll checks passed.")
    else:
        click.echo("\nSome checks failed. Fix the issues above.")
        sys.exit(1)


def _check_pass(msg: str) -> None:
    if sys.stdout.isatty():
        click.echo(f"  \033[32m[ok]\033[0m {msg}")
    else:
        click.echo(f"  [ok] {msg}")


def _check_fail(msg: str) -> None:
    if sys.stdout.isatty():
        click.echo(f"  \033[31m[!!]\033[0m {msg}")
    else:
        click.echo(f"  [!!] {msg}")


def _check_info(msg: str) -> None:
    if sys.stdout.isatty():
        click.echo(f"  \033[90m[--]\033[0m {msg}")
    else:
        click.echo(f"  [--] {msg}")
