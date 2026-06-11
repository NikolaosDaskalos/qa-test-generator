# Add explicit External Research Requests

Status: ready-for-agent
Type: AFK
User stories: 30-31

## What to build

Permit web research only when the user explicitly requests documentation, testing guidance, best practices, or other external information. Ordinary Repository questions must not have access to Tavily.

Answers that use web research must keep Repository sources and External References visibly separate, and External References must never be used as evidence for claims about Repository code or behavior.

## Acceptance criteria

- [ ] The question request can explicitly indicate an External Research Request.
- [ ] Ordinary Repository questions cannot invoke the web-search tool.
- [ ] Explicit external requests may invoke Tavily through a bounded research dependency.
- [ ] Repository claims remain grounded in Repository Evidence even when External References are present.
- [ ] Agent Stream and persisted results expose Repository sources and External References as separate collections.
- [ ] External research failures are sanitized and do not discard an otherwise valid repository-grounded answer.
- [ ] Tests prove that normal questions never call Tavily and explicit requests clearly separate both source types.

## Blocked by

- [06 - Stream repository-grounded answers with file citations](06-stream-grounded-answers-with-citations.md)

