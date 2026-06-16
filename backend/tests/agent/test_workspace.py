"""The generation workspace: clean branch prep, validated writes, canonical diff.

These exercise real Git against a throwaway checkout, so the workspace's branch
restoration and diff derivation are verified through the actual Git plumbing the
production path uses — no fakes.
"""

import subprocess
from pathlib import Path

from app.agent.workspace import LocalGitWorkspace
from app.schemas.generation import GeneratedFile


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a two-commit repo on ``main``; return the repo path and first commit SHA."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    (repo / "app").mkdir()
    (repo / "app" / "auth.py").write_text("def login():\n    return True\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "first")
    indexed_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "app" / "later.py").write_text("# added after indexing\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "second")
    return repo, indexed_sha


def test_prepare_branch_restores_indexed_commit_on_a_unique_non_default_branch(tmp_path: Path) -> None:
    """Branch prep checks out the indexed commit on a fresh non-default branch."""
    repo, indexed_sha = _init_repo(tmp_path)

    branch = LocalGitWorkspace(repo).prepare_branch(indexed_sha)

    assert branch != "main"
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == branch
    assert _git(repo, "rev-parse", "HEAD") == indexed_sha
    assert not (repo / "app" / "later.py").exists()


def test_discard_generation_restores_indexed_commit_and_removes_the_branch(tmp_path: Path) -> None:
    """Discarding a generation restores the indexed-commit tree and deletes the temporary branch."""
    repo, indexed_sha = _init_repo(tmp_path)
    workspace = LocalGitWorkspace(repo)
    branch = workspace.prepare_branch(indexed_sha)
    workspace.write_test_files([GeneratedFile(path="tests/test_auth.py", content="def test_login():\n    assert True\n")])

    workspace.discard_generation(indexed_sha, branch)

    # The working tree is back at the indexed commit: the generated Test File is gone and no diff remains.
    assert _git(repo, "rev-parse", "HEAD") == indexed_sha
    assert not (repo / "tests" / "test_auth.py").exists()
    assert _git(repo, "status", "--porcelain") == ""
    # The temporary generation branch no longer exists.
    branches = _git(repo, "branch", "--list", branch)
    assert branches == ""


def test_written_test_files_produce_a_canonical_unified_diff(tmp_path: Path) -> None:
    """Writing a validated Test File yields a Git unified diff naming the path and added content."""
    repo, indexed_sha = _init_repo(tmp_path)
    workspace = LocalGitWorkspace(repo)
    workspace.prepare_branch(indexed_sha)

    workspace.write_test_files([GeneratedFile(path="tests/test_auth.py", content="def test_login():\n    assert True\n")])
    diff = workspace.diff()

    assert "tests/test_auth.py" in diff
    assert "+def test_login():" in diff
    assert diff.startswith("diff --git")
