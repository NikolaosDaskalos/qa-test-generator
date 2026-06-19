"""Exceptions raised by the Git subprocess layer."""


class GitError(Exception):
    """A git-command execution error with a message."""

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)
