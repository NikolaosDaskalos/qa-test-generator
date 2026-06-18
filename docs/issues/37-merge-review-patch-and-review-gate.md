# Merge the Patch Review and its routing gate into one node

Status: ready-for-agent
Type: AFK
ADR: [0002 - Intent-routed unified LangGraph](../adr/0002-intent-routed-unified-langgraph.md)

## What to build

Collapse the separate `review_gate` routing node into `review_patch`. The reviewer
node continues to do exactly what it does today — run the static review, apply the
backend-owned threshold pass decision, independently re-verify the Test File
boundary, persist the verdict, and write a `ReviewResult` (and on an internal
error, a `RunFailure`) to state — and then **returns plain state**, never a
`Command(goto=...)`.

Post-review routing moves to an explicit conditional edge driven by a router
function returning a `Literal`: a reviewing-stage failure routes to the failure
sink; a below-threshold patch with Revision Budget remaining routes back to the
revision path; an accepted patch, or a below-threshold patch with the budget
exhausted, routes to the human decision, emitting the terminal `ReviewResult` on
that escalation as the gate does today. The `max_revision_attempts` configuration
moves onto the merged node's builder.

This removes a routing-only node and one use of `Command(goto=...)`, keeping all
control flow visible in the graph wiring.

## Acceptance criteria

- [ ] The `review_gate` node is removed; `review_patch` returns plain state and never returns a `Command`.
- [ ] A router function returning a `Literal` drives a conditional edge that reproduces the gate's three outcomes: revise, escalate to human decision, and fail.
- [ ] The terminal `ReviewResult` is emitted on escalation to the human decision (both accepted and budget-exhausted below-threshold), matching current behavior.
- [ ] `max_revision_attempts` is configured on the merged node's builder.
- [ ] A reviewing-stage failure routes to the failure sink via the router, not via a node-level goto.
- [ ] Tests covering review acceptance, below-threshold-with-budget revision, budget-exhausted escalation, and review failure pass.

## Blocked by

None - can start immediately.
