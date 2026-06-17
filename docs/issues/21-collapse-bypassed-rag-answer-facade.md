# Collapse the bypassed RAG answer facade

Status: ready-for-agent
Type: AFK
User stories: (refactor — supports the grounded-answer path behind US 06 "Stream grounded answers with citations")

## What to build

`RAGPipeline` is constructed only so the graph-wiring seam can pluck `.llm` and
`.document_retriever` off it. Its `answer_stream`, `set_system_prompt`, `ingest`,
and `get_stats` methods are dead on every live path, and `ChainBuilder`
duplicates the citation/answer logic that the `repository_question` graph nodes
(`retrieve` / `generate`) already own. The live ingestion path goes through
`DocumentIngestor` directly, not through the facade.

Collapse this pass-through end-to-end:

- Delete `ChainBuilder` (and its dedicated tests). The answer flow it used to own
  already lives in `repository_question.py` with its own de-duplicated citation
  helper — there should be exactly one citation helper, in that module.
- Delete the dead facade methods on `RAGPipeline` (`answer_stream`,
  `set_system_prompt`, `ingest`, `get_stats`) and the `chain_builder` member.
- Rewire the dependency-injection seam so the session graph is composed from the
  chat model + `DocumentRetriever` (+ `DocumentIngestor`) directly — the same way
  ingestion is already wired — instead of reaching past a facade for its
  internals. Retire/replace the `get_rag_pipeline` provider so nothing constructs
  the facade just to harvest its components.
- Update the tests that currently guard the deleted code so the suite passes.

After this change there is no `RAGPipeline`/`ChainBuilder` indirection between the
wiring seam and the components the graph actually needs.

## Acceptance criteria

- [ ] `app/rag/chain_builder.py` and its tests are deleted; no remaining import of
      `ChainBuilder` anywhere in `app/` or `tests/`.
- [ ] The dead `RAGPipeline` methods (`answer_stream`, `set_system_prompt`,
      `ingest`, `get_stats`) and the `chain_builder` attribute are removed; the
      bypassed facade no longer exists (or `RAGPipeline` is removed entirely if it
      retains no live responsibility).
- [ ] The session-graph wiring composes the chat model, `DocumentRetriever`, and
      `DocumentIngestor` directly at the dependency seam without reaching past a
      facade for `.llm` / `.document_retriever`.
- [ ] Citation logic lives in exactly one module (`repository_question.py`); no
      duplicate citation helper remains.
- [ ] The grounded-answer path (retrieve → generate → cited answer) behaves
      unchanged — verified by the existing `repository_question` / agent-stream
      tests still passing.
- [ ] The backend test suite passes (excluding the known environmental/pre-existing
      failures), with no test left guarding deleted code.

## Blocked by

None - can start immediately.
