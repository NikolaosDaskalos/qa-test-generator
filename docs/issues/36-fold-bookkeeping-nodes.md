# Fold pure-bookkeeping nodes into their neighbors

Status: completed
Type: AFK
ADR: [0002 - Intent-routed unified LangGraph](../adr/0002-intent-routed-unified-langgraph.md)

## What to build

Remove the two graph nodes whose only job is recorder calls and stage emission,
folding their work into the nearest node that does real work.

`persist_run` is absorbed into the `plan` node: planning becomes the
test-generation branch entry point and is responsible for creating the Coding Run
(which mints `coding_run_id`), advancing it into the planning stage, and emitting
the run-started and planning stage markers, before invoking the planner LLM. The
`classify` node routes a `test_generation` intent straight to `plan`.

`begin_retrieving` is absorbed into the `gather_evidence` node: gathering evidence
first advances the run into the retrieving stage and emits the retrieving marker,
then partitions evidence as before.

Behavior is unchanged end-to-end — the same recorder calls fire in the same order
and the same stage markers reach the Agent Stream; only the node boundaries move.
As today, an out-of-scope request still creates a run that is then failed in the
planning stage.

## Acceptance criteria

- [x] The `persist_run` and `begin_retrieving` nodes are removed from the graph.
- [x] `plan` creates and begins the Coding Run and emits the run-started and planning markers before planning; it gains the recorder and run config it needs.
- [x] `gather_evidence` advances the run to retrieving and emits the retrieving marker before partitioning evidence; it gains the recorder it needs.
- [x] `classify` routes the `test_generation` intent directly to `plan`.
- [x] The order of recorder calls and emitted stage markers across the run is unchanged.
- [x] Tests covering the test-generation branch are updated to the new node boundaries and pass.

## Blocked by

None - can start immediately.
