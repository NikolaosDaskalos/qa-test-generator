class IngestorError(ValueError):
    """Ingestor error with a message."""

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)


class RetrieverError(Exception):
    """Retriever error with a message."""

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)
