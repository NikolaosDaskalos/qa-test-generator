# Open a Pull Request on Approval via PyGithub

Status: ready-for-agent
Type: AFK
User stories: 106-118

## What to build

Extend Approval so that, after the approved generated branch is successfully pushed, the backend opens a GitHub Pull Request from that branch into the Repository's default branch. The PR body carries the Patch Review — the score, the configured pass threshold, and the categorized findings — so the owner reviews the proposed Test Files and the assessment together on GitHub.

GitHub API access uses the **PyGithub** library (new dependency), constructed with the Repository Credential and a configurable API base URL (default `https://api.github.com`, overridable for GitHub Enterprise). The `gh` CLI is not used.

Per ADR [0006](../adr/0006-open-pull-request-on-approval-via-pygithub.md), add `open_pull_request(...)` to the existing `PatchPublisher` port that the approve node already uses for `commit` and `push`. The production adapter owns the credential and the network; the existing fake keeps graph and node tests offline. The push happens first; the PR is opened only after a successful push.

PyGithub failures translate to a new sanitized `GitHubError` (mirroring `GitError`, Repository Credential redacted). Pull-request creation failure is a Run Failure on a new `github_pull_request` stage, distinct from `git_push`, because the branch is already on the remote. The Approval response surfaces the created Pull Request's URL to the owner.

This revises issue [15](15-approve-and-push-generated-branch.md), which stopped at the pushed branch and left PR creation manual.

## Acceptance criteria

- [ ] After a successful push on Approval, the backend opens a Pull Request from the generated branch into the Repository's default branch as the base.
- [ ] The Pull Request is opened only after the push succeeds; it is never opened when the push fails.
- [ ] The Pull Request body contains the Patch Review score, the configured pass threshold, and the categorized findings.
- [ ] GitHub API access uses PyGithub, authenticated with the same Repository Credential used for clone, fetch, and push, honoring a configurable API base URL.
- [ ] `open_pull_request` is added to the `PatchPublisher` port; the graph/approve node stays free of the network and the credential, and the existing fake publisher is used in graph and node tests.
- [ ] Approval still never pushes to or merges the Repository's default branch.
- [ ] The successful Approval response exposes the created Pull Request's URL to the owner.
- [ ] PyGithub failures are translated to a sanitized `GitHubError` with the Repository Credential redacted from messages and logs.
- [ ] A pull-request creation failure is recorded as Run Failure stage `github_pull_request`, distinct from `git_push`, conveying that the branch is pushed but the Pull Request was not opened.
- [ ] A credential lacking pull-request write permission produces a clear, sanitized failure on the `github_pull_request` stage.
- [ ] No Pull Request, issue, or comment is created on the question or rejection paths.
- [ ] Tests substitute a fake PyGithub client (no network) and cover: PR opened with the default branch as base, the Patch Review rendered in the body, the returned PR URL, push-then-PR ordering, credential redaction, the permission-denied failure stage, and the absence of any GitHub write on non-Approval paths.

## Blocked by

- [15 - Approve and push a protected generated branch](15-approve-and-push-generated-branch.md)
