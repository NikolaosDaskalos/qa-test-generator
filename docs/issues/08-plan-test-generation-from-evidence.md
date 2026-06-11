# Plan Test-Generation Tasks from Repository Evidence

Status: ready-for-agent
Type: AFK
User stories: 33-37, 53, 55, 70

## What to build

Start a Coding Run from a free-text Test-Generation Task submitted within a Repository Session. Introduce the bounded LangGraph plan and retrieve stages so the planner emits Research Intents and optional candidate paths, while the backend controls all actual evidence access.

Candidate paths are untrusted hints. Only normalized paths inside the Repository checkout and Repository Evidence returned by repository-scoped retrieval may enter later graph nodes.

## Acceptance criteria

- [ ] An authenticated owner can submit a non-empty Test-Generation Task for a ready Repository Session and receive an Agent Stream.
- [ ] Requests outside adding or improving tests are rejected before generation.
- [ ] A persisted Coding Run is created in `queued` state and advances through `planning` and `retrieving`.
- [ ] Coding Run persistence defines the planned state vocabulary, Repository and Repository Session ownership, failure stage, sanitized failure reason, and revision count needed by later graph stages.
- [ ] Planner output is structured as Research Intents with optional candidate Repository paths.
- [ ] Candidate paths are normalized, confined to the checkout, rejected when unsafe, and treated only as retrieval hints.
- [ ] The retrieve node uses the session's Repository identity and supplies only validated Repository Evidence.
- [ ] Agent Stream events expose ordered planning and retrieval progress and identify the persisted Coding Run.
- [ ] Model, migration, persistence, and deterministic graph tests cover valid planning, invalid task scope, unsafe path hints, empty evidence, state persistence, relationships, state values, and event ordering without external model calls.

## Blocked by

- [04 - Retrieve evidence only from the selected Repository](04-retrieve-repository-scoped-evidence.md)
- [05 - Create immutable Repository Sessions with bounded Session History](05-create-bound-repository-sessions.md)
