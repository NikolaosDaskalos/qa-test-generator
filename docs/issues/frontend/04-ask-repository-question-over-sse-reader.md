# Ask a Repository question over a bespoke SSE reader with live tokens and citations

Status: ready
Type: AFK
User stories: frontend bare-minimum copilot

## What to build

Deliver the core chat loop for repository questions, end to end through the streaming stack. The
user types a question against a ready repository and sees the answer stream in live, followed by its
file citations.

Because the generated client is axios-based and cannot stream, this slice introduces the
hand-written `fetch` + `ReadableStream` reader described in ADR-0003: an async generator that posts
to the session questions endpoint, reuses the generated client's base URL and stored bearer token,
parses `data: {json}` SSE lines, and yields the closed typed Agent Stream frame vocabulary. This
slice handles the repository-question path only — stage progress markers, streamed answer tokens,
and the single terminal `result` frame carrying the answer and citations. Test-generation terminals
are out of scope here (next slice).

Session handling follows the approved model: there is no list-sessions endpoint, so the active
session id is kept in browser storage keyed by repository. Selecting a repository resumes its last
active session and loads its history; a "New Session" action creates a fresh session and clears the
chat. Resumed history renders prior user/assistant messages with their citations.

## Acceptance criteria

- [ ] A bespoke SSE reader posts a question and yields typed Agent Stream frames, reusing the client's base URL and bearer token.
- [ ] Submitting a question renders a one-line stage status, streams answer tokens live into the assistant message, and on the terminal `result` shows the answer with its file citations as a source list.
- [ ] The active session id is persisted per repository in browser storage; reloading resumes the last session for the selected repository.
- [ ] On repository/session selection the chat loads and renders existing session history (messages and citations).
- [ ] A "New Session" action creates a new session, stores its id, and clears the chat.
- [ ] The chat input is usable only for a `ready` repository, and an out-of-band transport error frame is surfaced without crashing the page.

## Blocked by

- [03 - Register a Repository and wait until it is ready](03-register-repository-and-wait-until-ready.md)
