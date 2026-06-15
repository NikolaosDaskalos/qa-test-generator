# Add explicit External Research Requests

Status: superseded
Superseded by: [08 - Route Request Intent and plan Test-Generation Tasks](08-plan-test-generation-from-evidence.md), [09 - Generate canonical test patch](09-generate-canonical-test-patch.md)
Type: AFK
User stories: 30-31

## Why superseded

This issue proposed explicit External Research Requests on the repository-question path: a user could
opt a Repository question into Tavily web search, with External References kept separate from
Repository sources.

That direction was dropped. Web search is now confined to the **test-generation** path, where the
generator consults it (as a bounded ReAct tool) for a test framework's syntax and best practices —
see [ADR 0002](../adr/0002-intent-routed-unified-langgraph.md). Ordinary Repository questions never
reach the web. The `External Research Request` glossary term is removed; `External Reference` is
redefined accordingly in `CONTEXT.md`.

The surviving acceptance criteria — web search never invoked by a repository question, External
References kept separate from Repository Evidence and never grounding repository claims, sanitized
research failures that don't discard a valid result — are carried by issue 09.

## Original intent (for reference)

Permit web research only when the user explicitly requested documentation, testing guidance, best
practices, or other external information; ordinary Repository questions must not have access to
Tavily, and External References must never be used as evidence for claims about Repository code or
behavior.
