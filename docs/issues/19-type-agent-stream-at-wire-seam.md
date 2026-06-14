# Type the Agent Stream at the wire seam

Status: completed
Type: AFK

## What to build

Give the Agent Stream a closed, typed event vocabulary and produce the
server-sent event response from typed events at the wire seam. Today the stream
is untyped `dict`s with a stringly-typed `"type"` field, and four modules
(chain_builder, rag_pipeline, session_service, the route adapter) each know the
magic strings and payload keys. This slice introduces the typed union and makes
the Repository Session answer flow and the SSE adapter speak it end-to-end.

The answer chain builder may keep emitting its current dict events for now; they
are normalized into typed events by a small **temporary shim** at the pipeline
boundary. The shim is removed in the follow-up slice (issue 20), so the producer
is not rewritten here — this slice proves the type end-to-end at the wire.

Decisions already settled (see `CONTEXT.md` → *Agent Stream*):

- The union is **domain-only**: `Stage | Token | Sources | Citations | Result`.
  There is no `Error` member.
- **Deliberate** outcomes (insufficient evidence today; a rejected Test Patch or
  Run Failure later) are normal terminal `Result`-shaped events, never errors.
  Insufficient-evidence keeps streaming as a normal `Result` with empty citations.
- **Unexpected** failures (dropped connection, upstream crash) stay an
  out-of-band concern of the SSE adapter — one transport error frame — and are
  not part of the event vocabulary.
- The **double-`done` is collapsed**: the chain builder's internal
  "generation complete + sources" signal becomes a `Sources` event that the
  session service consumes internally and never forwards, so it never reaches the
  wire. Only the adapter emits a single terminal frame.
- The dead `token_info` cost estimate is dropped.
- Representation is **Pydantic models** (the app is already Pydantic/FastAPI), so
  the adapter serializes with `model_dump_json()` and is the only module that
  knows the wire format.

Event-union shape (from the design discussion — encodes the decisions precisely):

```python
class Citation(BaseModel):
    source: str

class Stage(BaseModel):
    type: Literal["stage"] = "stage"
    stage: Literal["retrieving", "generating"]

class Token(BaseModel):
    type: Literal["token"] = "token"
    content: str

class Sources(BaseModel):            # internal hop only; never serialized to the wire
    type: Literal["sources"] = "sources"
    sources: list[str]

class Citations(BaseModel):
    type: Literal["citations"] = "citations"
    citations: list[Citation]

class Result(BaseModel):             # terminal domain event
    type: Literal["result"] = "result"
    repository_session_id: UUID
    assistant_message_id: UUID
    answer: str
    citations: list[Citation]

AgentStreamEvent = Stage | Token | Sources | Citations | Result
```

## Acceptance criteria

- [x] A Pydantic event union (`Stage | Token | Sources | Citations | Result`) plus a `Citation` model exists in one module; each event carries a literal `type` discriminant.
- [x] The Repository Session answer flow yields typed events, and the SSE adapter is the only module that serializes them to the wire (via `model_dump_json()`).
- [x] The stream emits exactly one terminal frame — the double-`done` is gone — and `token_info` no longer appears anywhere in the stream.
- [x] Insufficient-evidence still streams as a normal terminal `Result` with empty citations (not an error).
- [x] An unexpected mid-stream failure still surfaces as a single out-of-band transport error frame, outside the typed vocabulary.
- [x] The chain builder's existing dict output is adapted into typed events by a temporary shim at the pipeline boundary (to be removed in issue 20).
- [x] `test_session_service` asserts an ordered sequence of typed events instead of magic-string dicts; the route/session test passes; the Postman acceptance assertion is updated to expect the single terminal frame.
- [x] The full backend test suite is green.

## Blocked by

None - can start immediately.
