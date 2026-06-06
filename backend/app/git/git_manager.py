"""
git/git_manager.py
-------------------
Git Manager to make handle git repositories cloning and branching
"""
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import giturlparse
from giturlparse import GitUrlParsed

from app.core.config import settings
from app.errors.git_errors import GitError

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    exit_code: int
    stdout: str
    stderr: str


class GitManager:

    # TODO add functionality for private repositories
    def __init__(self, repo_url: str) -> None:
        self._parsed_url: GitUrlParsed = self._parse_repo_url(repo_url)
        self._repo_path: Path = settings.REPO_PATH / self._parsed_url.name
        # Create the path if it does not exist
        self._repo_path.mkdir(parents=True, exist_ok=True)

    def clone(self) -> GitResult | None:
        print(self._repo_path)
        if self._repo_path.exists() and any(self._repo_path.iterdir()):
            logger.info(f"Repository {self._parsed_url.name} already exists")
            return None

        return self._run("git", "clone", self._parsed_url.url)

    def commit(self, commit_msg: str) -> GitResult:
        if not commit_msg:
            raise GitError("Commit message cannot be empty")

        if self._run("git", "add", ".").exit_code != 0:
            raise GitError("Git add process failed")

        return self._run("git", "commit", "-m", f"{commit_msg}")

    def push_current_branch(self) -> GitResult:
        if self._run("git", "branch", "--show-current").stdout.strip() in ['main', 'master']:
            raise ValueError("Push to 'main' or 'master' branch is not supported.")

        return self._run("git", "push", "origin", "HEAD")

    def get_default_branch(self) -> str:
        default_branch = self._run("git", "ls-remote", "--symref", self._parsed_url.url, "HEAD")
        for line in default_branch.stdout.splitlines():
            if line.startswith("ref: refs/heads/"):
                return line.removeprefix("ref: refs/heads/").split()[0]

        raise GitError("Default branch not found")

    def fetch(self):
        return self._run("git", "fetch", "origin")

    def checkout(self, branch_name: str) -> GitResult:
        if not branch_name:
            raise GitError("Branch name cannot be empty")

        branch_name: str = branch_name.strip()
        branch_exists = self._run("git", "ls-remote", "--heads", "origin", f"{branch_name}").stdout
        print(f"branch_exists: {branch_exists}")
        if not branch_exists:
            raise ValueError("Branch does not exist")

        return self._run("git", "checkout", "-B", "branch-name", f"origin/{branch_name}")

    def _run(self, *args: str) -> GitResult:
        result = subprocess.run(
            [*args],
            cwd=self._repo_path.resolve(),
            timeout=30,
            text=True,
            check=True,
            shell=False,
            capture_output=True,
        )

        return GitResult(
            exit_code=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )

    def _parse_repo_url(self, repo_url) -> GitUrlParsed:
        """Parses and validates repository URL."""
        if not repo_url:
            raise ValueError("Repository URL cannot be empty")

        parsed_url: GitUrlParsed = giturlparse.parse(repo_url.strip())
        if not parsed_url.valid:
            raise ValueError("Repository URL or SSH link is not valid")

        return parsed_url


# if __name__ == "__main__":
    # git = GitManager("git@github.com:NikolaosDaskalos/fastapi-heroes-app.git")
    # print(git.get_default_branch())
    # clone = git.clone()
    # print(f"clone: {clone}")
    # fetch = git.fetch()
    # print(f"fetch: {fetch}")
    # try:
    #     checkout = git.checkout('non-existing-branch')
    #     print(f"checkout: {checkout}")
    # except GitError as e:
    #     print(f"error: {e}")
