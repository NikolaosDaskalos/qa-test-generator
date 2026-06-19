"""Git integration: command execution and repository-URL parsing, re-exported as one surface."""

from app.integrations.git.git_commands import COMMIT_AUTHOR_EMAIL, COMMIT_AUTHOR_NAME, GitCommands
from app.integrations.git.git_process import GitResult, run_git
from app.integrations.git.repository_url import SUPPORTED_REPOSITORY_HOSTS, ParsedRepositoryUrl, parse_repository_url

__all__ = [
    "COMMIT_AUTHOR_EMAIL",
    "COMMIT_AUTHOR_NAME",
    "GitCommands",
    "GitResult",
    "run_git",
    "SUPPORTED_REPOSITORY_HOSTS",
    "ParsedRepositoryUrl",
    "parse_repository_url",
]
