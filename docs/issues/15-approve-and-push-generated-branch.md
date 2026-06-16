# Approve and push a protected generated branch

Status: completed
Type: AFK
User stories: 59, 61-68

## What to build

Allow the owner of a Coding Run in `awaiting_approval` to approve its reviewed Test Patch. Approval commits the current patch and pushes its unique generated branch with the Repository Credential, while failing closed against any attempt to push the Repository's default branch.

After a successful push, restore the local checkout to the indexed commit and remove the local generated branch. Keep the pushed remote branch available for manual inspection or pull-request creation.

## Acceptance criteria

- [x] Only the owning user may approve a Coding Run, and Approval is accepted only from `awaiting_approval`.
- [x] Approval commits exactly the reviewed Test Patch on its unique non-default branch.
- [x] The push uses the stored Repository Credential through non-interactive authentication without exposing it in commands, logs, or failures.
- [x] Push is rejected when the current branch is the default branch or either branch identity cannot be determined.
- [x] Commit failure records failure stage `git_commit`; push failure records failure stage `git_push`.
- [x] Provider and Git failure reasons are sanitized and the Repository Credential is redacted.
- [x] Successful Approval transitions the Coding Run to `approved`, restores the local checkout to the indexed commit, and removes the local generated branch.
- [x] The successfully pushed remote branch remains available and Repository Evidence is not changed.
- [x] Route, service, and Git tests cover ownership, state validation, commit, push, default-branch protection, redaction, failure stages, and cleanup.

## Blocked by

- [11 - Review a Test Patch before Approval](11-review-test-patch.md)
- [13 - Serialize and cancel active Coding Runs safely](13-serialize-and-cancel-coding-runs.md)
