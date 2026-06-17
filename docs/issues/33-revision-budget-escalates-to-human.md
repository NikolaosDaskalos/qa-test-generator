# Configurable Revision Budget that escalates to human review

Status: ready
Type: AFK
Revises: [12 - Perform one bounded Revision Attempt](12-perform-bounded-revision.md), [23 - Name the Revision Attempt budget](23-name-the-revision-attempt-budget.md)
ADR: [0004 - Scored Patch Review escalates to human review](../adr/0004-scored-review-escalates-to-human.md)

## What to build

Restructure the post-review loop so a low-scoring Test Patch is never shown to
the user as a failed run. Replace the implicit `_route_after_review`
conditional-edge function with an explicit `review_gate` graph node that reads
two state values — the review score and the spent Revision Budget — and routes
via `Command(goto=…)`:

- score at or above threshold → human review (`await_decision`)
- score below threshold with budget remaining → one more `revise_tests`
- score below threshold with budget exhausted → **also** human review,
  carrying the best attempt with its score and findings

Exhausting the budget escalates; it does not fail. The owner always gets to
inspect and approve or reject. `RunFailure` narrows to genuine stage errors
(generation crash, patch validation, git commit/push, review-engine crash) and
is no longer produced by a low review score.

The Revision Budget becomes configurable via a `MAX_REVISION_ATTEMPTS` setting
(default two). The budget module is generalized from the fixed single attempt to
a configurable limit; its "exhausted ⇒ reviewing-stage Run Failure" rule and the
`SECOND_REVIEW_REJECTED` reason are removed, and the `reject_run` node is
deleted. The glossary term has already moved from *Revision Attempt* to
*Revision Budget* in CONTEXT.md.

The human-in-the-loop interrupt at `await_decision` must surface the score and
findings (not just the diff) so the owner can judge a below-threshold patch. The
existing human reject path and its `RunRejected` terminal (issue 14) are
unchanged — only automatic failure on a low score is gone. `stream_session`
relays the resulting shrunken terminal-event set with no change to the typed
event contract.

## Acceptance criteria

- [ ] An explicit `review_gate` node owns post-review routing and replaces the `_route_after_review` edge function, routing via `Command(goto=…)`.
- [ ] A `MAX_REVISION_ATTEMPTS` setting (default 2) governs the Revision Budget; the budget module exposes a configurable limit and no longer encodes a failure outcome.
- [ ] Below-threshold scoring with remaining budget routes through `revise_tests`; with exhausted budget it routes to `await_decision`, not to failure.
- [ ] The `reject_run` node and the `SECOND_REVIEW_REJECTED` auto-failure are removed; `RunFailure` is produced only by genuine stage errors.
- [ ] `await_decision` surfaces the score and findings alongside the diff so the owner can judge an escalated below-threshold patch.
- [ ] The human reject path and `RunRejected` terminal are unchanged.
- [ ] `stream_session` relays the reduced terminal-event set with no change to the typed-event wire contract.
- [ ] Graph tests cover: accept at threshold, one revision then accept, budget exhausted then escalate-to-human (no `RunFailure`), a genuine stage error still failing, and budget configured to 0 and to >1.

## Blocked by

- [32 - Score a Test Patch out of ten](32-score-based-patch-review.md)
