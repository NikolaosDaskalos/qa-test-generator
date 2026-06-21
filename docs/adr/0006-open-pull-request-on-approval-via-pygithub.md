# Approval opens a Pull Request through the GitHub API via PyGithub

## Status

accepted

Revises issue [15](../issues/15-approve-and-push-generated-branch.md), which shipped Approval as a push that deliberately stopped at "keep the pushed remote branch available for manual inspection or pull-request creation."

## Context and decision

Approval (issue 15) commits the reviewed Test Patch on its unique non-default branch and pushes that branch with the Repository Credential, then stops. The owner is left to open the pull request by hand on GitHub. That manual last step breaks the otherwise end-to-end flow and discards context the backend already holds — the Patch Review score and findings — that belongs on the PR for the human deciding whether to merge.

We decided to extend Approval to **open a Pull Request from the pushed branch into the Repository's default branch**, carrying the Patch Review in the PR body.

- **PR creation is the API counterpart to the existing push, on the same seam.** The graph's approve node already talks to the `PatchPublisher` port (`commit`, `push`); we add `open_pull_request(...)` to that port. The graph stays free of the network and the Repository Credential exactly as it is today, and the existing fake `PatchPublisher` keeps graph/node tests offline. The push happens first; the PR is opened only after a successful push.
- **The GitHub API is reached through PyGithub, not the `git` protocol, raw httpx, or the `gh` CLI.** Opening a PR is an API operation the Git protocol cannot perform. We use the maintained `PyGithub` library rather than hand-rolling httpx calls (less request/pagination/error plumbing to own) or adding the `gh` binary to the container (no new system dependency, no subprocess seam to harden). PyGithub is constructed with the Repository Credential and a configurable API base URL (default `https://api.github.com`, overridable for GitHub Enterprise).
- **The Patch Review rides in the PR body.** The PR body includes the score, the configured pass threshold, and the categorized findings, so the owner reviews the proposed Test Files and the assessment together on GitHub. No separate issue or PR comment is created.
- **A new `GitHubError` mirrors `GitError`.** PyGithub failures are translated to a sanitized `GitHubError` (credential redacted), so the approve node's existing failure-stage handling extends rather than changes. PR-creation failure is a `Run Failure` on a new `github_pull_request` stage, kept distinct from `git_push`: the branch is already on the remote, so the failure means "branch pushed, Pull Request not opened."
- **Approval still never writes the default branch.** The PR proposes a merge into the default branch; it never pushes to or merges it. Default-branch protection in `push_current_branch` is unchanged, and merging the PR is the owner's decision on GitHub, outside the demo scope.

## Considered options

- **PyGithub vs. raw httpx vs. the `gh` CLI** — chose PyGithub. Raw httpx is lighter but makes us own auth headers, error mapping, and pagination for a growing API surface; the `gh` CLI adds a system binary and a second subprocess seam to harden alongside `run_git`. PyGithub gives a typed, maintained client for one new dependency, and is straightforward to fake at the adapter boundary. Cost: a sync library in an otherwise async-leaning backend (acceptable — Approval already runs synchronous Git subprocesses) and trusting a third party with the credential in-process.
- **Extend `PatchPublisher` vs. a standalone GitHub client called by the node** — chose extending the port. The approve node already owns commit-then-push through one port; adding the PR there keeps the credential and network in one production adapter and one fake, instead of teaching the node about a second collaborator. Cost: the `PatchPublisher` name now spans Git and GitHub-API operations.
- **Patch Review in the PR body vs. a follow-up PR comment vs. a tracking issue** — chose the PR body. The body is created atomically with the PR, needs no second API call that could partially fail, and is what a reviewer reads first. A comment is a second failure point; a tracking issue is a different workflow deferred as out of scope.
- **PR-creation failure: new `github_pull_request` stage vs. reuse `git_push`** — chose a new stage. Reusing `git_push` would mislead an owner into thinking the branch never landed. A distinct stage lets the failure say the branch is pushed and only the Pull Request is missing, so retry is cheap and non-destructive.
- **Open the PR before or after the push** — chose after. A PR cannot reference a branch the remote does not have; ordering push then PR keeps each step's failure attributable to its own stage.
