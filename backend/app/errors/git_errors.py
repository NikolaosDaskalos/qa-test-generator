class GitError(Exception):
    """A business-logic error with a code and message."""

    def __init__(self, msg: str):
        self.msg = msg
