import subprocess
import uuid
from base64 import b64encode
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.errors.git_errors import GitError
from app.git.git_commands import COMMIT_AUTHOR_EMAIL, COMMIT_AUTHOR_NAME, GitCommands
from app.git.git_process import GitResult
from app.git.repository_url import parse_repository_url


def test_git_repository_checkout_paths_are_isolated_by_user(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    first_user = uuid.uuid4()
    second_user = uuid.uuid4()
    repo_url = "https://github.com/openai/openai-python.git"

    parsed_repository_url = parse_repository_url(repo_url)
    first = GitCommands(parsed_repository_url, first_user)
    second = GitCommands(parsed_repository_url, second_user)

    assert first.repo_path != second.repo_path
    assert first.repo_path == (tmp_path / str(first_user) / "github.com" / "openai" / "openai-python")


def test_token_bearing_operations_always_send_authentication(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    token = "secret-token"

    git._run("git", "fetch", "origin", cwd=tmp_path, token=token)

    assert token not in captured["args"]
    assert captured["shell"] is False
    assert captured["env"]["QA_GIT_TOKEN"] == token
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert captured["env"]["GIT_ASKPASS"].endswith("git_askpass.py")
    encoded_credentials = b64encode(f"x-access-token:{token}".encode()).decode()
    assert captured["env"]["GIT_CONFIG_COUNT"] == "1"
    assert captured["env"]["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert captured["env"]["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {encoded_credentials}"


def test_validate_remote_access_uses_authenticated_ls_remote(monkeypatch) -> None:
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    calls = []

    def fake_run(*args: str, **kwargs) -> GitResult:
        calls.append((args, kwargs))
        return GitResult(stdout="", stderr="")

    monkeypatch.setattr(git, "_run", fake_run)

    git.validate_remote_access("replacement-token")

    assert calls == [
        (
            ("git", "ls-remote", "https://github.com/openai/openai-python.git"),
            {"cwd": Path.cwd(), "token": "replacement-token"}
        )
    ]


def test_get_current_commit_sha_resolves_head(monkeypatch) -> None:
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs) -> GitResult:
        calls.append(args)
        return GitResult(stdout="a" * 40, stderr="")

    monkeypatch.setattr(git, "_run", fake_run)

    assert git.get_current_commit_sha() == "a" * 40
    assert calls == [("git", "rev-parse", "HEAD")]


def test_commit_supplies_author_identity(monkeypatch) -> None:
    """The container has no global Git identity, so commits must carry one inline."""
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs) -> GitResult:
        calls.append(args)
        return GitResult(stdout="", stderr="")

    monkeypatch.setattr(git, "_run", fake_run)

    git.commit("Add generated tests")

    assert calls[0] == ("git", "add", ".")
    assert calls[1] == (
        "git",
        "-c",
        f"user.name={COMMIT_AUTHOR_NAME}",
        "-c",
        f"user.email={COMMIT_AUTHOR_EMAIL}",
        "commit",
        "-m",
        "Add generated tests",
    )


def test_commit_rejects_an_empty_message() -> None:
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())

    with pytest.raises(GitError, match="Commit message"):
        git.commit("")


def test_push_rejects_the_remote_default_branch(monkeypatch) -> None:
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    monkeypatch.setattr(git, "get_default_branch", lambda: "trunk")
    monkeypatch.setattr(git, "_run", lambda *args, **kwargs: GitResult(stdout="trunk", stderr=""))

    with pytest.raises(GitError, match="default branch"):
        git.push_current_branch("secret-token")


def test_push_rejects_when_the_current_branch_cannot_be_determined(monkeypatch) -> None:
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    monkeypatch.setattr(git, "_run", lambda *args, **kwargs: GitResult(stdout="", stderr=""))

    with pytest.raises(GitError, match="Current branch"):
        git.push_current_branch("secret-token")


def test_push_allows_a_non_default_branch(monkeypatch) -> None:
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs) -> GitResult:
        calls.append(args)
        if args == ("git", "branch", "--show-current"):
            return GitResult(stdout="feature/test-generation", stderr="")
        return GitResult(stdout="pushed", stderr="")

    monkeypatch.setattr(git, "get_default_branch", lambda: "trunk")
    monkeypatch.setattr(git, "_run", fake_run)

    result = git.push_current_branch("secret-token")

    assert result.stdout == "pushed"
    assert calls[-1] == ("git", "push", "origin", "HEAD")


def test_clone_accepts_equivalent_existing_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    (git.repo_path / ".git").mkdir(parents=True)
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return GitResult(stdout="git@github.com:openai/openai-python.git", stderr="")

    monkeypatch.setattr(git, "_run", fake_run)

    assert git.clone("secret-token") is None
    assert calls == [
        (("git", "remote", "get-url", "origin"), {"cwd": git.repo_path}),
        (("git", "ls-remote", "https://github.com/openai/openai-python.git"), {"cwd": Path.cwd(), "token": "secret-token"}),
    ]


def test_clone_rejects_different_existing_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    (git.repo_path / ".git").mkdir(parents=True)
    monkeypatch.setattr(git, "_run", lambda *args, **kwargs: GitResult(stdout="https://github.com/openai/openai-node.git", stderr=""))

    with pytest.raises(GitError, match="different repository"):
        git.clone("secret-token")


def test_delete_checkout_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    """Delete only the deterministic checkout and tolerate a retry."""
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    git.repo_path.mkdir(parents=True)
    (git.repo_path / "module.py").write_text("print('test')", encoding="utf-8")

    git.delete_checkout()
    git.delete_checkout()

    assert not git.repo_path.exists()


def test_delete_checkout_rejects_symlinks(monkeypatch, tmp_path: Path) -> None:
    """Refuse recursive deletion through a checkout-path symlink."""
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path / "repositories")
    git = GitCommands(parse_repository_url("https://github.com/openai/openai-python.git"), uuid.uuid4())
    outside = tmp_path / "outside"
    outside.mkdir()
    git.repo_path.parent.mkdir(parents=True)
    git.repo_path.symlink_to(outside, target_is_directory=True)

    with pytest.raises(GitError, match="symlink"):
        git.delete_checkout()

    assert outside.exists()
