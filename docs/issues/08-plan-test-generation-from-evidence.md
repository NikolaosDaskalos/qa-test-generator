# Route Request Intent and plan Test-Generation Tasks from Repository Evidence

Status: ready-for-agent
Type: AFK
User stories: 33-37, 53, 55, 70

## What to build

Make `POST /{repository_session_id}/questions` infer `Request Intent` and route a single unified
LangGraph `StateGraph` (one shared state object, compiled with a `MemorySaver` checkpointer) to one
of two branches. The request body and endpoint are unchanged — intent is inferred, not a client
field.

- A `classify` node (LLM, structured output) decides `repository_question | test_generation`.
  Uncertain classification falls back to `repository_question` (read-only, no side effects). It may
  read recent Session History so follow-ups ("now write tests for that") classify correctly.
- The `repository_question` branch re-homes the existing retrieval/answer logic as native
  `retrieve → generate` graph nodes and keeps the terminal `Result` (answer + citations) unchanged.
- The `test_generation` branch persists a `Coding Run` and runs the bounded `plan → retrieve`
  stages. The planner emits `Research Intents` (evidence to find, optional candidate Repository
  paths), tagged to target source code or existing tests. The backend controls all actual evidence
  access; candidate paths are untrusted hints.

Only normalized paths inside the Repository checkout and Repository Evidence returned by
repository-scoped retrieval may enter later graph nodes. A generic retrieve node executes the
planner's intents and partitions results into `source_evidence` (what's implemented) and
`test_evidence` (what's already tested), kept separate in state.

Generation, the `web_search` tool, and the `PatchResult` terminal are issue 09.

## Acceptance criteria

- [ ] `POST /questions` infers Request Intent via a `classify` node and routes the unified graph;
      the endpoint and request schema are unchanged.
- [ ] Uncertain classification routes to `repository_question`; the repository-question branch
      preserves the existing streamed answer and `Result` (answer + citations).
- [ ] An authenticated owner submitting a Test-Generation Task for a ready Repository Session
      receives an Agent Stream.
- [ ] Requests outside adding or improving tests are rejected at the `plan` stage as
      `RunFailure(failed_stage=planning)` before generation.
- [ ] A persisted Coding Run is created in `queued` state and advances through `planning` and
      `retrieving`; the per-run checkpointer `thread_id` is persisted on the Coding Run.
- [ ] Coding Run persistence defines the planned state vocabulary, Repository and Repository Session
      ownership, failure stage, sanitized failure reason, and revision count needed by later stages.
- [ ] Planner output is structured as Research Intents with optional candidate Repository paths,
      tagged source vs. test.
- [ ] Candidate paths are normalized, confined to the checkout, rejected when unsafe, and treated
      only as retrieval hints.
- [ ] The retrieve node uses the session's Repository identity and supplies only validated
      Repository Evidence, partitioned into separate `source_evidence` and `test_evidence`.
- [ ] Agent Stream events expose ordered `classifying`/`planning`/`retrieving` progress (via
      `messages`/`custom` stream modes mapped onto the typed `AgentStreamEvent` union) and identify
      the persisted Coding Run.
- [ ] Model, migration, persistence, and deterministic graph tests cover routing both intents,
      valid planning, invalid task scope, unsafe path hints, empty evidence, source/test partition,
      state persistence, relationships, state values, and event ordering without external model
      calls.

## Blocked by

- [04 - Retrieve evidence only from the selected Repository](04-retrieve-repository-scoped-evidence.md)
- [05 - Create immutable Repository Sessions with bounded Session History](05-create-bound-repository-sessions.md)
- [06 - Stream repository-grounded answers with file citations](06-stream-grounded-answers-with-citations.md)

## Design

See [ADR 0002 - Intent-routed unified LangGraph for repository sessions](../adr/0002-intent-routed-unified-langgraph.md).
