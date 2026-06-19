# Reorganize Repository Sessions

Status: completed
Type: AFK
User stories: 18-29, 32, 87-103

## What to build

Consolidate the Repository Session lifecycle into a feature-oriented module covering creation, ownership, listing, history, question execution, Coding Run lookup, human decisions, and Agent Stream coordination. Keep FastAPI routing and SSE serialization as thin inbound adapters while preserving the single intent-routed questions entry point.

The restructure must preserve Session History chronology, Repository scoping, durable Coding Run references, pagination behavior, recent-context limits, streaming, and human-in-the-loop resume behavior.

## Acceptance criteria

- [x] Repository Session schemas, workflows, execution, history behavior, and authorization rules have one predictable feature-oriented home.
- [x] Repository Session and Session History database records and persistence adapters have explicit placement under the shared database structure.
- [x] HTTP routes perform request/response translation while session workflows remain free of FastAPI-specific exceptions and response types.
- [x] SSE serialization remains the only module aware of wire framing and preserves the closed Agent Stream vocabulary.
- [x] The unified questions endpoint still handles Repository questions, Code Generation Tasks, and resumed human decisions.
- [x] Repository ownership, history ordering, pagination, recent AI context, Coding Run recovery, and disconnect handling remain unchanged.
- [x] API, persistence, streaming, graph-resume, and frontend integration tests pass through the reorganized imports.

## Blocked by

- [Issue 48](48-rename-code-generation-and-review-workflow.md)
- [Issue 49](49-reorganize-repository-lifecycle.md)
