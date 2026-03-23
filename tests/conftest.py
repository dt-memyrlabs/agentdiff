import os
import sys
from pathlib import Path

import pytest

# Ensure src is on the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def project_dir(tmp_path):
    """Create a temporary project directory with .agentdiff/ structure."""
    agentdiff_dir = tmp_path / ".agentdiff" / "sessions"
    agentdiff_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def git_project_dir(tmp_path):
    """Create a temporary project directory with git initialized."""
    import subprocess
    agentdiff_dir = tmp_path / ".agentdiff" / "sessions"
    agentdiff_dir.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
    return tmp_path
