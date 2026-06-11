# Serialize and cancel active Coding Runs safely

Status: ready-for-agent
Type: AFK
User stories: 56-58, 64-65, 67-68

## What to build

Protect the shared Repository checkout by permitting at most one active Coding Run per Repository. Detect Agent Stream disconnects and other abandoned processing, record a terminal Run Failure, discard unapproved changes, restore the indexed commit, and remove the local temporary branch.

This is deterministic single-process demo coordination, not production-grade distributed locking.

## Acceptance criteria

- [ ] Starting a Coding Run is rejected while the same Repository already has a run in an active state.
- [ ] Runs for different Repositories do not block one another.
- [ ] Client disconnect during generation or review cancels processing and records a sanitized terminal Run Failure.
- [ ] Cancellation, generation failure, and validation failure discard all unapproved working-tree changes.
- [ ] Cleanup restores the checkout to the indexed default-branch commit and removes the local temporary branch.
- [ ] Cleanup is safe to retry and does not remove a successfully pushed remote branch.
- [ ] Coding Run state-transition rules reject invalid or duplicate terminal transitions.
- [ ] Service and graph tests cover active-run conflicts, disconnect cancellation, failure cleanup, idempotent cleanup, and persisted failure stages.

## Blocked by

- [09 - Generate canonical diffs for existing Test Files](09-generate-canonical-test-patch.md)

