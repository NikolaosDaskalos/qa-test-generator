# Unify error handling and remove the last Command(goto)

Status: completed
Type: AFK
ADR: [0002 - Intent-routed unified LangGraph](../adr/0002-intent-routed-unified-langgraph.md)

## What to build

Finish the routing convention so no node hides control flow from the graph wiring,
and centralize what happens when an unexpected error occurs in any step.

Extract a single failure helper that every node's exception handler calls to build
the user-safe `RunFailure` state for its stage (replacing the per-node inline
construction and the `_fail_with`/`_continue_to` helpers). The `fail_run` node
becomes the one thin terminal sink that records the failure on the Coding Run,
stamps the run identifier onto the event, and emits it — reached only because every
router checks for a failure on state first and routes a `"failed"` literal to it.

Convert the final `Command(goto=...)` user, the approval node, to the same pattern:
it returns plain state (an approval result, or a failure on a commit/push error),
and a router function returning a `Literal` routes to the failure sink or to the
end of the run.

The end state: every node returns plain state, all routing is expressed as
conditional edges with `Literal`-returning router functions, and unexpected errors
in any step flow through one helper to one sink.

## Acceptance criteria

- [x] A single failure helper builds the user-safe `RunFailure` state and is used by every node's exception handler.
- [x] No node in the graph returns a `Command(goto=...)`; the dead `_fail_with`/`_continue_to` helpers are removed.
- [x] The approval node returns plain state and is routed by a `Literal`-returning router to either the failure sink or the run's end.
- [x] `fail_run` remains the single sink that records, stamps, and emits the failure, reached via `"failed"` literals from routers that check state first.
- [x] A commit/push failure during approval routes to the failure sink and ends the run as a failure; a successful approval ends the run approved.
- [x] Tests covering each stage's failure path and the approval success/failure paths pass.

## Blocked by

- [37 - Merge the Patch Review and its routing gate into one node](37-merge-review-patch-and-review-gate.md)
- [38 - Merge the generating-stage nodes into one generate_tests node](38-merge-generating-nodes.md)
