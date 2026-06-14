# Emit typed Agent Stream events from the producer

Status: ready-for-agent
Type: AFK

## What to build

Finish the Agent Stream deepening by moving typed-event production into the
answer chain builder and removing the temporary shim introduced in issue 19.
After this slice, the chain builder yields `Token` and `Sources` events
natively, and no module anywhere converts event dicts into typed events — the
typed union is the single home for the stream's shape.

This is an internal cleanup with **no observable behavior change**: the wire
output is byte-for-byte the same happy path as after issue 19. The value is
locality — dict-shape knowledge of the Agent Stream now lives nowhere outside
the union module.

## Acceptance criteria

- [ ] The answer chain builder yields typed `Token` and `Sources` events directly, with no intermediate event dicts.
- [ ] The temporary normalization shim from issue 19 is deleted; no module converts event dicts into typed events.
- [ ] `test_chain_builder` asserts typed `Token`/`Sources` events rather than dict shapes.
- [ ] No event-dict literals (e.g. `{"type": "token"...}`, `{"type": "done"...}`) remain in the answer-stream path outside the union module.
- [ ] The wire output, the full backend test suite, and the Postman acceptance check remain green with no observable change.

## Blocked by

- Issue 19 (Type the Agent Stream at the wire seam)
