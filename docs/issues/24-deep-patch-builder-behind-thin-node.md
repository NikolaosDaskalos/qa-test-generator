# Give the patch-build step a deep interface behind a thin node

Status: completed
Type: AFK
User stories: 9 (refactor under issue 09 — "Generate the canonical Test Patch")

## What to build

The patch-build step's `validate → write → diff → persist` sequence is currently
interleaved with state-dictionary plumbing inside a graph-node closure, and the
reviewer independently re-runs the same Test-File boundary check. Its only
interface today is "populate the shared state, compile the graph, invoke it" — so
the real bugs live in the wiring, not in the already-deep path/test-file
validators it calls underneath.

Pull the orchestration into a deep `PatchBuilder` that takes plain inputs
(validated proposals, checkout root, whether this is a Revision Attempt, the
generation branch, Coding Run id, External References) and returns either a
Test Patch result or a typed Run Failure — never an escaping exception and never
a raw state dict. The boundary re-check the reviewer performs is the same
validation; expose it as one shared boundary verifier so both the builder and the
review step ask the same module instead of duplicating the `validate_test_file`
loop. The `build_patch` graph node shrinks to a thin adapter that unpacks state,
calls the builder, and folds the result (or failure) back onto state.

End to end, behavior is unchanged: unsafe paths / non-Python / application-code
proposals are still generating-stage Run Failures raised before any write, the
workspace is still reset on a Revision Attempt before re-writing, the canonical
diff still comes from Git, the Coding Run is still persisted, and a patch that
escapes Test-File scope is still rejected at review even when the reviewer
accepts.

## Acceptance criteria

- [x] A deep `PatchBuilder` owns validate → write → diff → persist, taking plain
      inputs and returning a Test Patch result or a typed Run Failure (no raw
      state dict, no escaping exception).
- [x] The Test-File boundary check is a single shared verifier used by both the
      builder's validation and the review step's independent re-check (no
      duplicated `validate_test_file` loop).
- [x] The `build_patch` graph node is a thin adapter: unpack state → call builder
      → fold result/failure onto state.
- [x] The builder and the boundary verifier are unit-tested directly with plain
      inputs, without compiling or running the graph — including the failure
      mapping (rejected path, derivation failure) in isolation.
- [x] Behavior is preserved: pre-write validation failures, Revision-Attempt
      workspace reset, Git-derived diff, Coding Run persistence, and review-time
      boundary rejection all still hold.
- [x] The backend suite passes excluding known environmental/pre-existing
      failures.

## Blocked by

None - can start immediately.
