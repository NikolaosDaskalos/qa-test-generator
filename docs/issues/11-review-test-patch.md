# Review a Test Patch before Approval

Status: ready-for-agent
Type: AFK
User stories: 47-50, 54-55

## What to build

Add the Patch Review graph stage after a Test Patch is generated. The reviewer must assess the patch against the original Test-Generation Task, retrieved Repository Evidence, existing test conventions, visible imports, unrelated changes, and the Test File boundary.

Patch Review is evidence-based static assessment only. It must not execute generated tests, install dependencies, or imply runtime correctness.

## Acceptance criteria

- [ ] A generated Coding Run enters `reviewing` and invokes Patch Review with the task, Repository Evidence, complete proposals, and canonical diff.
- [ ] Patch Review returns a structured accepted or rejected decision with human-readable findings.
- [ ] Review checks task alignment, existing test conventions, imports visible in Repository Evidence, unrelated changes, and Test File-only scope.
- [ ] The backend independently verifies the Test File boundary even when the reviewer accepts the patch.
- [ ] An accepted first review transitions the Coding Run to `awaiting_approval`.
- [ ] Reviewer findings, final diff, and the persisted run result are emitted through the Agent Stream.
- [ ] Owned run lookup and patch lookup endpoints expose persisted Coding Run state, Test Patch content, Patch Review findings, failure information, and the canonical diff after streaming ends.
- [ ] User-visible output states that tests were not executed and runtime correctness was not verified.
- [ ] Route and deterministic graph tests cover lookup ownership, accepted and rejected reviews, unrelated changes, invalid imports, source-file changes, persisted findings, and event order.

## Blocked by

- [09 - Generate canonical diffs for existing Test Files](09-generate-canonical-test-patch.md)
- [10 - Allow new Test Files only in existing test roots](10-allow-new-files-in-existing-test-roots.md)
