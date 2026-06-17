# Own the terminal event where it is produced

Status: completed
Type: AFK
User stories: (refactor — supports the test-generation terminal events behind US 09 / 11–14: PatchResult, ReviewResult, approval/rejection, RunFailure)

## What to build

Today the graph produces the typed terminal events, but the session service
re-derives *which one wins* by scanning a fixed tuple of state keys —
`("failure", "rejection_result", "approval_result", "review_result", "patch_result")` —
in an implicit, hand-maintained precedence. Adding a new terminal means slotting
it into that tuple by hand, and the streaming seam leaks into the service.

Move terminal ownership to where the terminal is decided: each terminal
graph node emits its own typed terminal event onto the `custom` stream, exactly
the way `Stage` and `Token` markers already ride that stream. The stream adapter
forwards it like any other custom marker. The session service stops inspecting
final graph state for a terminal and just relays what the stream yields.

**Execution order replaces the hand-maintained tuple as the precedence
mechanism**: because only the terminal node that actually runs emits its event,
the precedence that the tuple encoded by hand (a reviewing-stage failure /
rejection / approval winning over an accepted review still sitting in
accumulated state) falls out of which node executed — no key-sniffing, no
ordered tuple to maintain. This applies on both the initial stream path and the
HITL resume path.

### Sanctioned contract change

This deliberately supersedes the existing contract documented in
`app/agent/stream.py` and assumed by `RepositorySessionService` —
*"Terminal domain events are decided by the caller from final state."* That line
and the matching service docstrings must be updated to the new rule: **terminal
domain events are emitted by their producing node and forwarded by the adapter;
the caller no longer derives them from final state.** This reverses a decision
referenced around ADR-0002; note the supersession where the contract is
documented so the change reads as intentional, not a regression.

The `repository_question` answer path (which persists the exchange and assembles
`Result` from final state because it needs the DB-written assistant message id)
is out of scope — this slice is the test-generation terminal tuple.

## Acceptance criteria

- [x] Each test-generation terminal node (reviewing-stage failure, rejection,
      approval, accepted review, generated patch) emits its own typed terminal
      event onto the stream instead of only stamping a state key.
- [x] The session service no longer scans the
      `("failure", "rejection_result", "approval_result", "review_result", "patch_result")`
      precedence tuple; the `_test_generation_terminal` key-sniffing helper is
      removed.
- [x] Terminal precedence is preserved through execution order on both the
      initial stream and the HITL resume path — a reviewing-stage failure,
      rejection, and approval still take precedence over an accepted review that
      remains in accumulated state.
- [x] The `stream.py` contract docstring and the service docstrings are updated to
      state that terminals are emitted by their producing node, with a note that
      this supersedes the prior "caller decides from final state" contract.
- [x] The `repository_question` → `Result` path is unchanged.
- [x] Tests assert terminal selection at the node/stream surface (not by poking
      final-state keys); the backend suite passes excluding known
      environmental/pre-existing failures.

## Blocked by

None - can start immediately.
