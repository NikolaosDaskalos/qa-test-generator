# Run a Test-Generation Task and render the reviewed Test Patch

Status: ready
Type: AFK
User stories: frontend bare-minimum copilot

## What to build

Extend the same chat input so that a test-generation request flows through end to end and shows its
reviewed result. The user does not choose a mode — intent is classified server-side — so a
test-generation request is just another message in the same unified chat.

Reuse the SSE reader from the prior slice to handle the test-generation frame set: ordered stage
markers (planning, retrieving, researching, generating, reviewing, revising, re-reviewing), the
mid-stream `run_started` frame that identifies the Coding Run, and the terminal frames. On a
completed review, render the review verdict (accepted/rejected), the reviewer findings, the
canonical diff in a preformatted block, and the static-review disclaimer. On a failed run, render
the failed stage and sanitized reason. An accepted review leaves the run awaiting the owner's
decision; the approve/reject controls themselves are the next slice.

## Acceptance criteria

- [ ] A test-generation message streams stage progress and renders the captured Coding Run id from the `run_started` frame.
- [ ] A completed review renders the verdict, findings, canonical diff in a preformatted block, and the disclaimer.
- [ ] A failed run renders its failed stage and sanitized reason as a normal terminal outcome (not an error).
- [ ] Test-generation and repository-question turns coexist in the same unified chat history.
- [ ] An accepted review visibly indicates the run is awaiting the owner's decision (controls added in the next slice).

## Blocked by

- [04 - Ask a Repository question over a bespoke SSE reader with live tokens and citations](04-ask-repository-question-over-sse-reader.md)
