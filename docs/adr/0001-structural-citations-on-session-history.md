# Store Session History citations structurally, not as a rendered footer

## Status

accepted

## Context and decision

Citations used to cross the persistence seam as a Markdown footer (`\n\n---\n📚 Sources: …`)
appended into the assistant message `content`. The reformulation read path then stripped it back
off by splitting on the `📚` literal. This made the footer format a hidden, untyped contract
duplicated across two modules (`session_service._with_citation_footer` produced it,
`chain_builder._to_lc_messages` consumed it); changing the format in one place silently broke
reformulation and could leak a citation into a follow-up query.

We now store citations **structurally** on `SessionHistory` in a `JSONB` column
(`citations`, `NOT NULL DEFAULT '[]'`), keeping them distinct from the answer text. Reformulation
reads the clean `content` directly; the read endpoint exposes `citations` as a structured field on
`SessionHistoryPublic`, symmetric with the live terminal `Result` event. The `📚` marker and the
footer format are removed from all live code paths.

## Considered options

- **JSONB column vs. a separate citation table** — chose the column. Citations are a small,
  ordered, already-de-duplicated value list owned by exactly one message, never queried
  independently. This mirrors the existing `source_document.doc_metadata` JSONB column; a table
  would add a join, an FK lifecycle, and an explicit order column for no in-scope benefit.
- **Citation type location** — the model defines a local `CitationData` TypedDict for the stored
  shape (mirroring `SourceDocumentMetadata`) rather than importing `Citation` from the Agent Stream
  vocabulary (`app.schemas.agent_stream`). This keeps the persistence layer free of any dependency
  on the event/wire schema; the one-field duplication is the same trade the codebase already made
  for `SourceDocumentMetadata`. The service serializes `Citation → dict` at the persist boundary.
- **Existing `📚`-footer rows** — not migrated. Session History is disposable course-capstone data,
  so no backfill is written and the transitional split is deleted outright rather than kept as a
  permanent read-path. Pre-existing rows simply age out.
