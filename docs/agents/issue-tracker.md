# Issue tracker: Local Markdown

Issues and PRDs for this repo live as markdown files under `docs/`.

## Conventions

- Implementation issues are flat files: `docs/issues/<NN>-<slug>.md`, numbered from `01`.
- The PRD lives at `docs/prd/PRD.md`.
- Each issue file opens with a short metadata header near the top:
  - `Status:` — the triage state (see `triage-labels.md` for the role strings)
  - `Type:` — e.g. `AFK` for agent-ready work
  - `User stories:` — the PRD user stories this slice covers
- The body uses `## What to build`, `## Acceptance criteria` (checkboxes), and any further sections the work needs.
- Comments and conversation history append to the bottom of the file under a `## Comments` heading.

## When a skill says "publish to the issue tracker"

Create a new file at `docs/issues/<NN>-<slug>.md`, picking the next free `<NN>`. Publish PRDs to `docs/prd/PRD.md`.

## When a skill says "fetch the relevant ticket"

Read the file under `docs/issues/`. The user will normally pass the path or the issue number directly.
