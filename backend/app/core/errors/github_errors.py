"""Exceptions raised by the GitHub API layer."""


class GitHubError(Exception):
    """A GitHub API error with a sanitized message (Repository Credential redacted)."""

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)
