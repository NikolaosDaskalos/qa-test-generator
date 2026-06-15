# Intent-routed unified LangGraph for repository sessions

## Status

accepted

## Context and decision

`POST /{repository_session_id}/questions` used to have exactly one behaviour: a repository-grounded
answer streamed by `ChainBuilder`. We need the same single endpoint to also start a Test-Generation
Task, without adding a second endpoint or an explicit client-supplied mode flag. We decided the
front door **infers `Request Intent`** with an LLM `classify` node and routes a single unified
LangGraph `StateGraph` (one shared state object) to one of two branches:

- **`repository_question`** — the existing retrieval/answer logic, re-homed as native
  `retrieve → generate` graph nodes; terminal `Result`.
- **`test_generation`** — persists a `Coding Run`, then `plan → retrieve → generate`. The planner
  emits `Research Intents` tagged source/test and validates scope; one generic retrieve node
  partitions Repository Evidence into `source_evidence` (what's implemented) and `test_evidence`
  (what's already tested); the generator is a ReAct loop whose only tool is `web_search`. Terminal
  `PatchResult` or `RunFailure`.

The graph is compiled with a `MemorySaver` checkpointer and a per-run `thread_id` (persisted on the
Coding Run) **now**, even though no node interrupts yet, so the human-in-the-loop patch review
(issues 11–14) slots in without re-architecting. Token streaming is preserved end-to-end:
`llm.stream()` inside nodes rides LangGraph's `"messages"` stream mode while stage markers ride
`"custom"`, and a thin adapter maps both onto the existing typed `AgentStreamEvent` union so the SSE
wire seam is unchanged.

## Considered options

- **Inferred intent vs. an explicit request field** — chose an LLM classifier. The product
  requirement is that the user just asks; a mode flag pushes intent detection onto the client and
  contradicts the single-question entry point. Uncertain classification falls back to
  `repository_question`, which is read-only, so a misroute never triggers side effects.
- **Unified graph vs. a thin router dispatching to the untouched flows** — chose one graph with
  native nodes. The repo-question and test-gen branches share retrieval (`DocumentRetriever`) and one
  state object; keeping the answer flow outside the graph would split the routing/state logic across
  two worlds. Cost: `ChainBuilder`'s token streaming had to move onto LangGraph's streaming API.
- **Checkpointer now vs. when HITL lands** — chose to add `MemorySaver` now as a foundation. It
  introduces a second state store (graph checkpoint vs. the durable DB `Coding Run`), so the rule is:
  checkpoint = in-flight graph state, DB = the domain record of truth. Note `MemorySaver` is
  in-process and ephemeral; cross-request HITL resume (issues 11–14) will need a durable checkpointer
  (e.g. a Postgres saver), and the per-run `thread_id` already lives on the Coding Run for that.
- **Web search confined to test generation** — `web_search` (Tavily) is reachable only on the
  `test_generation` path, as a bounded generator tool for a framework's current syntax and best
  practices. Its results are `External Reference`s, kept separate from Repository Evidence and never
  grounding claims about the Repository's code. This supersedes issue 07 (explicit External Research
  Requests on the repository-question path) and the `External Research Request` glossary term;
  ordinary Repository questions never reach the web.
