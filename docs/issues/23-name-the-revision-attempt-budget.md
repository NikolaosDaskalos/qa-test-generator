# Name the Revision Attempt budget

Status: ready-for-agent
Type: AFK
User stories: 51 (refactor under issue 12 — "Perform one bounded Revision Attempt")

## What to build

The *Revision Attempt* invariant — a named glossary term in CONTEXT.md ("the
single opportunity for the test generator to correct a Test Patch rejected by
Patch Review; a second rejection fails the Coding Run and prevents Approval") —
is currently encoded as a raw `int` plus truthiness checks scattered across the
graph router and several nodes, with a magic failure-reason string imported
*back* from `test_generation` into `graph.py`. Tracing "how many revisions, then
what happens" means bouncing between three sites.

Give the budget a home: one small module that owns the revision count and the
"exhausted → reviewing-stage Run Failure" rule (including the
`SECOND_REVIEW_REJECTED` reason). The post-review router and the revise / build /
review nodes ask the budget instead of reading an int's truthiness, so the
single-attempt rule is stated once and the cross-module back-import disappears.

End to end, behavior is unchanged: a first Patch Review rejection still routes
through exactly one Revision Attempt, a second rejection is still a terminal
reviewing-stage Run Failure (never an unbounded retry), and the re-review/reset
behavior that today keys off `revision_attempts` truthiness still fires on the
revised pass.

## Acceptance criteria

- [ ] A single module owns the Revision Attempt count and the
      "exhausted ⇒ reviewing-stage Run Failure (`SECOND_REVIEW_REJECTED`)" rule;
      the invariant "exactly one Revision Attempt" is expressed once.
- [ ] The post-review router decides revise-vs-reject by asking the budget, not by
      reading a raw int's truthiness.
- [ ] The revise, build-patch, and review-patch nodes consult the budget for
      "are we on/after the revision attempt" (re-review stage marker, workspace
      reset) rather than re-reading the raw count independently.
- [ ] `graph.py` no longer imports `SECOND_REVIEW_REJECTED` (or the count
      semantics) back from `test_generation`; the magic string lives with the
      budget.
- [ ] The budget is unit-tested in isolation without compiling or running the
      graph (fresh budget, after-one-spend, exhausted → failure).
- [ ] Existing graph tests still cover the accepted path, one Revision Attempt,
      and the second-review failure; the backend suite passes excluding known
      environmental/pre-existing failures.

## Blocked by

None - can start immediately.
