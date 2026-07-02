# Issue tracker: GitHub Issues

Implementation issues for this repo live as GitHub issues. Use the `gh` CLI to
read, create, and update them. PRDs still live as markdown under `docs/`.

## Conventions

- Issues live on GitHub: `gh issue list`, `gh issue view <number>`.
- The PRD lives at `docs/prd/PRD.md`.
- Triage state is carried by GitHub labels (see `triage-labels.md`).
- Each issue body should cover the same ground the old templates did:
  - the PRD user stories the slice covers,
  - `## What to build`,
  - `## Acceptance criteria` (checkboxes),
  - and any further sections the work needs.
- Conversation history lives in the issue's GitHub comments.

## Common `gh` commands

- List issues: `gh issue list --limit 50`
- Filter by triage label: `gh issue list --label ready-for-agent`
- View an issue: `gh issue view <number>`
- Create an issue: `gh issue create --title "..." --body "..." --label <label>`
- Comment: `gh issue comment <number> --body "..."`
- Re-label: `gh issue edit <number> --add-label <label> --remove-label <label>`
- Close: `gh issue close <number>`

## When a skill says "publish to the issue tracker"

Create a new GitHub issue with `gh issue create`, applying the appropriate
triage label. Publish PRDs to `docs/prd/PRD.md`.

## When a skill says "fetch the relevant ticket"

Read the GitHub issue with `gh issue view <number>`. The user will normally pass
the issue number directly.
