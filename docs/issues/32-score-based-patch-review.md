# Score a Test Patch out of ten

Status: completed
Type: AFK
Revises: [11 - Review a Test Patch before Approval](11-review-test-patch.md)
ADR: [0004 - Scored Patch Review escalates to human review](../adr/0004-scored-review-escalates-to-human.md)

## What to build

Change Patch Review from a model-decided boolean verdict to a backend-decided
threshold over a reviewer **score**. The reviewer returns a `score` out of ten
plus its categorized findings and no longer returns an `accepted` flag. The
backend owns the pass decision: a patch is accepted when its score meets a
configurable threshold (default seven), and the independent Test File boundary
check still hard-fails any escaping patch regardless of score, so the reviewer
is never the sole gate.

This slice is deliberately backward-compatible with the existing post-review
routing: the review node still derives and carries `accepted` on its result, so
the current revise/reject/approve routing keeps working unchanged. Restructuring
the loop is the next slice.

The score also surfaces on the Agent Stream. `ReviewResult` carries `score` and
the `threshold` it was judged against so a client can show "8/10 — passed". The
internal-only `PatchResult` (built into graph state but never emitted on the
wire) leaves the `AgentStreamEvent` union while remaining an internal state type.

## Acceptance criteria

- [x] The reviewer's structured output is a `score` (0–10) and categorized findings; it no longer returns an `accepted` boolean.
- [x] A new `REVIEW_PASS_THRESHOLD` setting (default 7) governs the pass decision; `accepted` is derived as `score >= threshold` in the backend, not by the model.
- [x] The Test File boundary check still forces rejection of any escaping patch even when the score is at or above threshold.
- [x] `ReviewResult` carries `score` and `threshold`; the derived `accepted` is still present so existing routing is unaffected by this slice.
- [x] `PatchResult` is removed from the `AgentStreamEvent` union and retained as an internal state type; nothing on the wire changes shape except `ReviewResult`'s new fields.
- [x] The user-visible "tests were not executed / runtime correctness not verified" disclaimer is unchanged.
- [x] Reviewer and graph tests cover scores below, at, and above threshold, a boundary escape overriding a high score, and the new `ReviewResult` fields.

## Blocked by

None - can start immediately.
