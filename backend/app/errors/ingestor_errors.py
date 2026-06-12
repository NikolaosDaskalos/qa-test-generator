class IngestorError(Exception):
    """Ingestor error with a message."""

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)
