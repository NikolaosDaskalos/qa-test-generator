# Merge the generating-stage nodes into one generate_tests node

Status: ready-for-agent
Type: AFK
Revises: [34 - Collapse to a single generator agent](34-single-generator-agent.md)
ADR: [0002 - Intent-routed unified LangGraph](../adr/0002-intent-routed-unified-langgraph.md)

## What to build

Collapse the four generating-stage nodes — branch preparation, initial
generation, revision, and patch building — into a single `generate_tests` node
that runs the whole generating stage end-to-end.

The node distinguishes its two modes with the existing Revision Budget signal
(`is_revision_attempt`). On the first pass it prepares the clean generation branch
at the indexed commit and calls the generator's initial generation; on a revision
pass it skips branch preparation (the branch already exists) and calls the
generator's revision with the prior proposal, the reviewed diff, and the findings,
spending one unit of the Revision Budget. Either way it then validates, writes, and
derives the canonical Test Patch. The post-review "revise" arm routes back to this
same `generate_tests` node.

All `Command(goto=...)` returns from the former nodes are removed: `generate_tests`
returns plain state, and a router function returning a `Literal` drives a
conditional edge to either patch review (success) or the failure sink (any
generating-stage failure: branch preparation, generation, revision, or patch
validation/build).

## Acceptance criteria

- [ ] The `prepare_branch`, `revise_tests`, and `build_patch` nodes are removed; their work lives inside `generate_tests`.
- [ ] `generate_tests` prepares the branch only on the first pass and skips it on a revision pass, selecting initial generation vs. revision via the Revision Budget signal.
- [ ] A revision pass spends one unit of the Revision Budget and carries the prior proposal, reviewed diff, and findings into the generator.
- [ ] The node validates, writes, and derives the canonical Test Patch on both passes.
- [ ] `generate_tests` returns plain state; a `Literal`-returning router drives the edge to review on success and to the failure sink on any generating-stage failure.
- [ ] The post-review revision arm targets `generate_tests`.
- [ ] The correct stage markers (generating vs. revising, and re-reviewing downstream) are emitted across both passes.
- [ ] Tests covering initial generation, a revision pass, branch-preparation failure, generation/revision failure, and patch-build failure pass.

## Blocked by

- [37 - Merge the Patch Review and its routing gate into one node](37-merge-review-patch-and-review-gate.md)
