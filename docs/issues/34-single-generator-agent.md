# Collapse to a single generator agent for generate and revise

Status: completed
Type: AFK
Revises: [12 - Perform one bounded Revision Attempt](12-perform-bounded-revision.md)
ADR: [0004 - Scored Patch Review escalates to human review](../adr/0004-scored-review-escalates-to-human.md)

## What to build

Remove the separate, deliberately tool-free revision agent. One
`web_search`-capable agent performs both initial generation and revision. The
revision-specific context — the prior complete-file proposal, the canonical diff
that was reviewed, and the reviewer's findings — continues to ride in the human
message that the revision prompt assembles, so the single agent has everything
it needs to produce a corrected full-file proposal.

This reverses the earlier "revision is deliberately tool-free" constraint:
revision may now call `web_search`, which is desirable because many findings
(e.g. a deprecated test-framework API) are exactly what a web lookup resolves.
The dedicated `REVISION_SYSTEM_PROMPT` retires into the assembled human message.

This slice is orthogonal to the loop restructure: the generator's `generate` and
`revise` call signatures are unchanged, so it can land independently.

## Acceptance criteria

- [x] The generator holds a single agent; the separate revision agent is removed.
- [x] Both generation and revision go through the one `web_search`-capable agent.
- [x] `REVISION_SYSTEM_PROMPT` is removed; revision context (prior proposal, diff, findings) is carried in the assembled human message.
- [x] The `generate` and `revise` interfaces consumed by the graph nodes are unchanged.
- [x] Generator tests cover initial generation and a revision pass through the single agent, including a revision that consults `web_search`.

## Blocked by

None - can start immediately.
