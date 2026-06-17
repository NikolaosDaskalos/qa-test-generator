# Close the Agent Stream wire seam by removing the dead Answer event

Status: ready-for-agent
Type: AFK
User stories: (refactor — tightens the typed Agent Stream wire seam from issues 19/20, supports ADR-0002)

## What to build

`AgentStreamEvent` claims to be the closed wire vocabulary, but its union still
carries an `Answer` member that is never serialized to the wire. The member's own
docstring describes an internal hop — "the chain builder emits one at the end of
a turn and the session service consumes it to persist the exchange and build the
terminal `Result`." That design was superseded: the answer path now records the
answer text and citations onto shared state, and the session service reads final
state to assemble and yield the terminal `Result`. As a result `Answer` is never
constructed anywhere in application code and never emitted — it is vestigial dead
code, and it is the only non-wire member of an otherwise all-wire union.

Remove the `Answer` model and its union membership so `AgentStreamEvent` is
honestly "wire events only," and update the module docstring that still describes
the `Answer` internal hop. This reaches the report's intended end state — a closed
wire seam where the SSE adapter serializes only public domain events — with a
deletion. No public/internal type split is introduced, because no live internal
event exists to justify the structure; the answer path's use of shared state is
unchanged.

End to end, behavior is unchanged: a Repository question still streams `Stage` /
`Token` events and terminates with a `Result` built from the persisted exchange;
the SSE adapter still serializes exactly the events it does today.

## Acceptance criteria

- [ ] The `Answer` model is removed and dropped from the `AgentStreamEvent` union;
      the union now contains only events that are serialized to the wire.
- [ ] The `agent_stream` module docstring no longer describes an `Answer` internal
      hop.
- [ ] A repository-wide check confirms nothing constructs or pattern-matches
      `Answer` (it was referenced only by its own definition and the union).
- [ ] The answer path's shared-state → final-state `Result` behavior is unchanged.
- [ ] The backend suite passes excluding known environmental/pre-existing failures.

## Blocked by

None - can start immediately. Independent of issues 26 and 27.
