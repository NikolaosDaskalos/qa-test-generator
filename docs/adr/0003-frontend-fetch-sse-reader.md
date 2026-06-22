# Frontend reads the Agent Stream with a bespoke fetch reader, not the generated client

## Status

accepted

## Context and decision

The frontend's HTTP layer is a generated hey-api client configured with the `legacy/axios`
plugin (`frontend/openapi-ts.config.ts`), and all repository/session CRUD goes through it. But the
core of the product — `POST /sessions/{repository_session_id}/questions` — returns
`text/event-stream` and is the only way to ask a Repository question, start a Code Generation Task,
or deliver the human-in-the-loop Approval decision. Axios buffers the whole response body, so the
generated client physically cannot surface the `Agent Stream` frame-by-frame.

We decided to **keep the generated axios client for every non-streaming endpoint and hand-write a
single `fetch` + `ReadableStream` async generator for the `/questions` stream.** The helper reuses
the same base URL (`OpenAPI.BASE`) and `localStorage` bearer token as the generated client, parses
`data: {json}` SSE lines, and yields the closed typed `AgentStreamEvent` vocabulary (`stage`,
`token`, `result`, `run_started`, `review_result`, `patch_result`, `run_failure`, `run_approved`,
`run_rejected`). The same generator serves questions, code generation, and the approve/reject
decision, since all three share the one endpoint.

## Considered options

- **Bespoke fetch reader vs. swapping the whole client generator to a streaming-capable transport**
  — chose the bespoke reader. Switching the generator (e.g. away from `legacy/axios`) would
  regenerate and revalidate every CRUD call across the app to fix one endpoint; an ~80-line helper
  isolates the streaming concern to exactly where it's needed.
- **SSE vs. WebSocket** — not reopened. The `Agent Stream` is deliberately SSE on the backend
  (see `CONTEXT.md`); the frontend mirrors that contract rather than introducing a second protocol.
- **Live frames vs. awaiting only the terminal frame** — chose to render frames live (stage status
  + streamed tokens), which is the whole point of using a reader instead of buffering; awaiting only
  the terminal event would have made the generated client nearly sufficient and defeated the choice.

## Consequences

- Two HTTP paths coexist in the frontend (generated client for CRUD, hand-written reader for the
  stream). A future reader seeing the bespoke reader should know it exists *because* the generated
  client cannot stream — not regard it as an inconsistency to "clean up."
- The reader must keep its base-URL and auth wiring in sync with `OpenAPI.BASE`/`OpenAPI.TOKEN`; the
  generated client owns that configuration and the reader borrows it.
