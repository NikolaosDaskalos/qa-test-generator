# Issue Tracker: Local Markdown

Issues and PRDs for this repository live as Markdown files in `doc/`.

## Conventions

- One feature per directory: `doc/<feature-slug>/`
- The PRD is `doc/<feature-slug>/PRD.md`
- Implementation issues are `doc/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`
- Triage state is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append under a `## Comments` heading

## Publishing

When a skill says to publish to the issue tracker, create the relevant file under `doc/<feature-slug>/`, creating the directory if needed.

## Fetching

When a skill says to fetch a ticket, read the referenced file. The user will normally provide its path or issue number.
