# Tell the owner where the approved branch was pushed

Status: ready
Type: AFK
Revises: [15 - Approve and push the generated branch](15-approve-and-push-generated-branch.md)
ADR: [0004 - Scored Patch Review escalates to human review](../adr/0004-scored-review-escalates-to-human.md)

## What to build

When the owner approves a reviewed Test Patch and its branch is pushed, give
them an explicit, ready-to-show feedback message rather than only the raw branch
name. The approval terminal event carries a human-readable message, composed by
the backend at approval time, naming the pushed branch and directing the owner
to open it on their repository — e.g. "Your tests were pushed to branch
'<name>'. Open it on your repository to review."

The branch name and diff already on the approval terminal are unchanged; this
adds the prepared message so any client renders consistent copy.

## Acceptance criteria

- [ ] `RunApproved` carries a `message` string composed at the approval node, naming the pushed branch.
- [ ] The message is produced only on a successful push; a commit/push failure remains a `RunFailure` with no approval message.
- [ ] The existing `branch`, `diff`, and disclaimer fields are unchanged.
- [ ] Tests assert the approval terminal includes the branch-naming message on a successful push.

## Blocked by

None - can start immediately.
