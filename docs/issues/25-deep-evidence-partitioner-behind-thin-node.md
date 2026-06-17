# Give the evidence-partition step a deep interface behind a thin node

Status: completed
Type: AFK
User stories: 8 (refactor under issue 08 — "Plan Test Generation from Evidence")

## What to build

The generic retrieve step partitions Repository Evidence into `source_evidence`
(what's implemented) and `test_evidence` (what's already tested) by walking the
planner's Research Intents, retrieving per intent, routing each batch by the
intent's source/test tag, and de-duplicating confined candidate-path hints — all
interleaved with shared-state plumbing inside a graph-node closure. Its only
interface is "populate state, compile the graph, invoke it."

Pull the partitioning into a deep evidence partitioner that takes plain inputs
(the Research Intents, the retriever, the checkout root / repository id) and
returns the partitioned source/test evidence plus the de-duplicated hints. The
`gather_evidence` graph node shrinks to a thin adapter that unpacks state, calls
the partitioner, and folds the partitioned result back onto state.

End to end, behavior is unchanged: each Research Intent is still retrieved and
routed to source vs. test by its tag, candidate paths are still confined to the
checkout before becoming hints, and hints are still de-duplicated in first-seen
order.

## Acceptance criteria

- [x] A deep evidence partitioner owns the per-intent retrieve, source/test
      routing, candidate-path confinement, and hint de-duplication, taking plain
      inputs and returning partitioned evidence + hints.
- [x] The `gather_evidence` graph node is a thin adapter: unpack state → call
      partitioner → fold partitioned evidence/hints onto state.
- [x] The partitioner is unit-tested directly with a fake retriever and plain
      Research Intents, without compiling or running the graph (source/test
      routing, hint confinement, de-duplication order).
- [x] Behavior is preserved: intents route to the correct partition, hints are
      confined to the checkout, and de-duplication keeps first-seen order.
- [x] The backend suite passes excluding known environmental/pre-existing
      failures.

## Blocked by

None - can start immediately. Independent of issue 24 (PatchBuilder).
