# Reject and discard a reviewed Test Patch

Status: ready-for-agent
Type: AFK
User stories: 59-60, 64-65

## What to build

Allow the owner of a Coding Run in `awaiting_approval` to reject its reviewed Test Patch. Rejection must persist the user's decision, discard all generated changes, restore the checkout to the indexed commit, and remove the local temporary branch without publishing anything.

## Acceptance criteria

- [ ] Only the owning user may reject a Coding Run.
- [ ] Rejection is accepted only from `awaiting_approval`.
- [ ] A successful rejection transitions the Coding Run to `rejected`.
- [ ] Rejection discards the Test Patch from the working tree while preserving its persisted review record for inspection.
- [ ] The checkout returns to the indexed commit and the local generated branch is removed.
- [ ] No commit, push, remote branch creation, or Repository Evidence update occurs.
- [ ] Repeated rejection and rejection from any other state are rejected without corrupting the checkout.
- [ ] Route and service tests cover ownership, state validation, persisted outcome, Git cleanup, and absence of remote operations.

## Blocked by

- [11 - Review a Test Patch before Approval](11-review-test-patch.md)
- [13 - Serialize and cancel active Coding Runs safely](13-serialize-and-cancel-coding-runs.md)

