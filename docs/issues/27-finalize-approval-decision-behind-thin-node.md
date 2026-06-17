# Give the approval decision a deep finalizer behind thin nodes

Status: ready-for-agent
Type: AFK
User stories: 14-15 (refactor — Approval decision finalization)

## What to build

The owner's approve/reject decision is finalized inside two graph-node closures.
`approve_patch` commits the reviewed Test Patch, pushes the branch with the
Repository Credential, records the run approved, and restores the checkout —
mapping a commit or push failure to a `git_commit` / `git_push` Run Failure along
the way. `discard_patch` restores the checkout, removes the temporary branch, and
records the run rejected. Both interleave this orchestration with shared-state
plumbing, and both repeat the same checkout-restore/cleanup step. Their only
interface is "populate state, resume the graph, invoke it."

Pull the orchestration into one deep `DecisionFinalizer` with `approve` and
`discard` methods that take plain inputs (a publisher, a workspace, the recorder,
the Coding Run id, the generation branch, the assessed diff, the indexed commit
sha, the review findings) and return a typed outcome — `RunApproved` /
`RunRejected`, or a `RunFailure` for a `git_commit` / `git_push` failure — never
an escaping exception and never a raw state dict. The shared checkout-restore /
branch-cleanup lives once inside the finalizer. The `approve_patch` and
`discard_patch` graph nodes shrink to thin adapters that unpack state, call the
finalizer, **emit** the returned terminal event, and fold it onto state.

Emission stays at the node: issue 22 ("Own the terminal event where it is
produced") established that terminal events are emitted by their producing graph
node, so the finalizer returns the typed outcome and the thin node emits it —
the same result-or-failure contract `PatchBuilder` (issue 24) already uses. The
finalizer holds no wire knowledge.

End to end, behavior is unchanged: an approval still commits exactly the reviewed
patch on its unique non-default branch, pushes it with the credential, records the
run approved, and restores the checkout (leaving the pushed remote branch intact);
a commit failure still short-circuits before push and a push failure is still a
`git_push` Run Failure; a rejection still discards the working-tree changes and
removes the temporary branch with local Git only while preserving the review
record; and the same terminal `RunApproved` / `RunRejected` / `RunFailure` still
reaches the Agent Stream.

## Acceptance criteria

- [ ] A deep `DecisionFinalizer` owns commit → push → record-approved → cleanup
      (approve) and discard → record-rejected (reject), taking plain inputs and
      returning a typed `RunApproved` / `RunRejected` / `RunFailure` outcome (no
      raw state dict, no escaping exception).
- [ ] The shared checkout-restore / branch-cleanup step is written once inside the
      finalizer, not duplicated across the two paths.
- [ ] The `approve_patch` and `discard_patch` graph nodes are thin adapters:
      unpack state → call finalizer → emit the returned terminal → fold onto state
      (emission stays at the node per issue 22).
- [ ] The finalizer is unit-tested directly with fake publisher / workspace /
      recorder, without resuming or running the graph: commit-then-push-then-
      approve-then-cleanup order, the discard-then-reject path, a commit failure
      short-circuiting before push, and a push failure after a successful commit.
- [ ] Behavior is preserved: existing graph and HITL-resume tests pass unchanged;
      the backend suite passes excluding known environmental/pre-existing failures.

## Blocked by

None - can start immediately. Soft-ordered after issue 26 (Coding Run lifecycle):
not a hard prerequisite, but sequencing after it lets the finalizer inherit the
typed `CodingRunStage` failure stage and named recorder transitions and avoids a
merge clash on `run_recorder.py` / `agent_stream.py`.
