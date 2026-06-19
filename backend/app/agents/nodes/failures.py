"""The single failure-state helper every node's exception handler funnels through.

A node that hits an unexpected error folds a user-safe ``RunFailure`` onto the
shared state through ``fail_state`` rather than constructing the state dict inline
or hiding control flow in a ``Command(goto=...)``. Routing stays in the graph: a
router checks ``state["failure"]`` first and routes a ``"failed"`` literal to the
single ``fail_run`` sink, which records, stamps, and emits the failure.
"""

from app.schemas import RunFailure


def fail_state(failure: RunFailure, *, trace: str) -> dict:
    """Build the canonical failure graph state for a stage's user-safe ``RunFailure``.

    The node names its stage and sanitized reason by passing a built ``RunFailure``;
    this returns the shared ``{"failure", "trace"}`` shape the routers read. The node
    does not emit — the ``fail_run`` sink owns the single terminal emission.
    """
    return {"failure": failure, "trace": [trace]}
