# Stream repository-grounded answers with file citations

Status: ready-for-agent
Type: AFK
User stories: 23-29, 32, 72

## What to build

Allow a user to ask a question within a Repository Session and receive an Agent Stream grounded only in that session's Repository Evidence. Recent Session History may reformulate follow-up questions, but claims about code and behavior must come from retrieved evidence and include inspectable file citations.

When relevant evidence is unavailable, the answer must state that limitation instead of filling gaps from model knowledge.

## Acceptance criteria

- [ ] The question endpoint returns a synchronous `text/event-stream` response for an owned Repository Session.
- [ ] Follow-up reformulation uses no more than the six most recent Session History messages.
- [ ] Retrieval is always bound to the Repository Session's immutable Repository identity.
- [ ] Agent Stream events include ordered stage progress, answer tokens, file citations, and one terminal persisted result.
- [ ] Every Repository citation identifies a source file from retrieved Repository Evidence and is traceable to the evidence supplied to generation.
- [ ] Answers do not cite or claim facts from another Repository or unsupported model knowledge.
- [ ] Empty or below-threshold evidence produces an explicit insufficient-evidence answer.
- [ ] The completed exchange and citations are persisted as Session History or associated question-result data.
- [ ] SSE tests consume complete streams and assert content type, event order, citations, insufficient evidence, persistence, authentication, and ownership.

## Blocked by

- [04 - Retrieve evidence only from the selected Repository](04-retrieve-repository-scoped-evidence.md)
- [05 - Create immutable Repository Sessions with bounded Session History](05-create-bound-repository-sessions.md)

