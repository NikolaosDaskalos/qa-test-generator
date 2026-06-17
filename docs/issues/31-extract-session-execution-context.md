# Extract the Repository Session execution-context assembly

Status: completed
Type: AFK
User stories: (refactor — narrows the session-stream input assembly behind US 06 answering / test-generation streaming)

## What to build

`stream_session` mixes several concerns in one method: it enforces ownership,
retrieves the recent Session History window and converts it to LangChain
messages, resolves the bound Repository's `checkout_root` and
`indexed_commit_sha`, assembles the graph input dict, drives the stream, and
persists the answer exchange. There is no duplication and a single call site, so
this is a focused readability/testability extraction, not a de-duplication.

Extract only the **execution-context assembly** — "what the graph needs to run
for this session" — into a small `RepositorySessionExecution` context: given the
session (and the stores, or the already-resolved Repository and history), it
resolves the checkout fields, projects the recent Session History window into
LangChain messages, and builds the graph input. `stream_session` keeps the
ownership check and continues to drive the Agent Stream events; the answer-
terminal persistence (append-exchange + building the terminal `Result` from final
state) stays where it is, so ADR-0001's structural Session History citations are
untouched.

The payoff is the stated one: the input assembly becomes unit-testable on plain
inputs without compiling or running the graph, and `stream_session` reads as
"authorize → assemble context → stream → persist answer."

End to end, behavior is unchanged: the same recent-history window becomes the
same messages, the same checkout fields are resolved (including the
missing-Repository → `None` case), the same graph input keys are produced, and the
answer exchange is still persisted with structural citations before the terminal
`Result` is yielded.

## Acceptance criteria

- [x] A `RepositorySessionExecution` context module owns checkout-field
      resolution, history-window → LangChain message projection, and graph-input
      assembly, taking plain inputs.
- [x] `stream_session` keeps the ownership check and stream driving and obtains
      its graph input from the context; the method no longer inlines history
      conversion / checkout resolution / input-dict construction.
- [x] Answer-terminal persistence and ADR-0001 structural citations are unchanged.
- [x] The context is unit-tested directly without compiling or running the graph:
      checkout-field resolution including the missing-Repository `None` case, the
      role → message projection, and the graph-input keys.
- [x] Behavior is preserved: existing session-stream tests pass unchanged; the
      backend suite passes excluding known environmental/pre-existing failures.

## Blocked by

None - can start immediately. Touches the same file as issue 26 (which moves the
`awaiting_decision` precondition); sequence after 26 or coordinate to avoid a
`session_service.py` merge clash.
