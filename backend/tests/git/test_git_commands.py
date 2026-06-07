import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.errors.git_errors import GitError
from app.git.git_commands import GitCommands, GitResult
from app.git.repository_url import parse_repository_url


def test_repository_checkout_paths_are_isolated_by_user(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    first_user = uuid.uuid4()
    second_user = uuid.uuid4()
    repo_url = "https://github.com/openai/openai-python.git"

    repository = parse_repository_url(repo_url)
    first = GitCommands(repository, first_user)
    second = GitCommands(repository, second_user)

    assert first.repo_path != second.repo_path
    assert first.repo_path == (
        tmp_path / str(first_user) / "github.com" / "openai" / "openai-python"
    )


def test_token_is_passed_only_through_askpass_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    git = GitCommands(
        parse_repository_url("https://github.com/openai/openai-python.git"),
        uuid.uuid4(),
    )
    token = "secret-token"

    git._run("git", "fetch", "origin", cwd=tmp_path, token=token)

    assert token not in captured["args"]
    assert captured["shell"] is False
    assert captured["env"]["QA_GIT_TOKEN"] == token
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert captured["env"]["GIT_ASKPASS"].endswith("git_askpass.py")


def test_push_rejects_the_remote_default_branch(monkeypatch) -> None:
    git = GitCommands(
        parse_repository_url("https://github.com/openai/openai-python.git"),
        uuid.uuid4(),
    )
    monkeypatch.setattr(git, "get_default_branch", lambda: "trunk")
    monkeypatch.setattr(
        git,
        "_run",
        lambda *args, **kwargs: GitResult(stdout="trunk", stderr=""),
    )

    with pytest.raises(GitError, match="default branch"):
        git.push_current_branch("secret-token")


def test_push_allows_a_non_default_branch(monkeypatch) -> None:
    git = GitCommands(
        parse_repository_url("https://github.com/openai/openai-python.git"),
        uuid.uuid4(),
    )
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


def test_clone_accepts_equivalent_existing_origin(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    git = GitCommands(
        parse_repository_url("https://github.com/openai/openai-python.git"),
        uuid.uuid4(),
    )
    (git.repo_path / ".git").mkdir(parents=True)
    monkeypatch.setattr(
        git,
        "_run",
        lambda *args, **kwargs: GitResult(
            stdout="git@github.com:openai/openai-python.git",
            stderr="",
        ),
    )

    assert git.clone("secret-token") is None


def test_clone_rejects_different_existing_origin(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "REPO_PATH", tmp_path)
    git = GitCommands(
        parse_repository_url("https://github.com/openai/openai-python.git"),
        uuid.uuid4(),
    )
    (git.repo_path / ".git").mkdir(parents=True)
    monkeypatch.setattr(
        git,
        "_run",
        lambda *args, **kwargs: GitResult(
            stdout="https://github.com/openai/openai-node.git",
            stderr="",
        ),
    )

    with pytest.raises(GitError, match="different repository"):
        git.clone("secret-token")
