# Deepen the Coding Run lifecycle behind named transitions

Status: completed
Type: AFK
User stories: 13-15 (refactor under the Coding Run lifecycle)

## What to build

The Coding Run's status sequence currently leaks into its callers. Graph nodes
name the target status themselves — `advance(coding_run_id, CodingRunStatus.planning)`,
`...retrieving`, `...generating`, `...reviewing` — scattered across the unified
graph and the test-generation branch, so the lifecycle order lives in the nodes
rather than in one place. The persistence port accepts an arbitrary status, so
nothing enforces or even names the legal sequence. Failure stages cross the seam
as bare string literals (`"generating"`, `"reviewing"`, `"git_commit"`,
`"git_push"`) that the recorder coerces back into an enum. And the
"is this run resumable for an owner decision" precondition lives as a raw enum
comparison inside the session-stream resume path.

Deepen the existing `RunRecorder` so it owns the transitions instead of taking
dictation. Replace the generic `advance(id, status)` with intention-named
transition methods (`begin_planning`, `begin_retrieving`, `begin_generating`,
`begin_reviewing`) that each encode their own target status; remove `advance`
from the public port. The recorder Protocol and both implementations (the
`CodingRunStore`-backed adapter and the null adapter) move in lockstep; the
store stays the dumb persistence adapter it already is. Type the failure stage
as the `CodingRunStage` enum where it is produced so nodes reference the enum
rather than loose strings and the recorder drops its string-to-enum coercion.
Move the resume precondition onto the Coding Run entity as an `awaiting_decision`
predicate so the session-stream path reads a domain property instead of
comparing the status enum directly.

This is explicitly the **state/transitions** slice. The Git side-effects of
approval and rejection — commit, push, discard, checkout cleanup — and the
terminal `RunApproved` / `RunRejected` event emission are **out of scope** here;
they belong to the Approval decision finalization issue.

End to end, behavior is unchanged: a run still moves queued → planning →
retrieving → generating → reviewing → awaiting-approval/changes-requested →
approved/rejected, still stamps the same failure stage and sanitized reason on a
Run Failure, and is still only resumable for a decision while awaiting approval.

## Acceptance criteria

- [x] The `RunRecorder` port exposes intention-named transition methods that each
      encode their own target status; the generic `advance(id, status)` is gone
      from the public interface.
- [x] The Protocol, the `CodingRunStore`-backed recorder, and the null recorder
      all move together; the store remains the persistence-only adapter.
- [x] The failure stage is typed as the `CodingRunStage` enum where it is
      produced; nodes reference the enum and the recorder no longer coerces a
      string into the enum.
- [x] The Coding Run entity exposes an `awaiting_decision` predicate, and the
      session-stream resume path reads it instead of comparing the status enum.
- [x] No `advance(... CodingRunStatus ...)` status-literal calls remain in the
      unified graph or the test-generation branch.
- [x] The deepened recorder transitions and the `awaiting_decision` predicate are
      unit-tested directly against a fake/in-memory store, without compiling or
      running the graph.
- [x] Behavior is preserved: existing graph and session-stream tests pass
      unchanged (pure behavior-preserving refactor); the backend suite passes
      excluding known environmental/pre-existing failures.

## Blocked by

None - can start immediately. The Approval decision finalization issue (Git
side-effects + terminal events) builds on this but does not block it.
