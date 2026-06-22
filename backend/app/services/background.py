"""The seam through which services enqueue request-independent background work."""

from collections.abc import Callable
from typing import Any, Protocol


class BackgroundScheduler(Protocol):
    """Schedule a callable to run after the response is returned.

    FastAPI's ``BackgroundTasks`` satisfies this structurally, keeping the HTTP
    transport type out of feature workflows.
    """

    def add_task(self, func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> None: ...
