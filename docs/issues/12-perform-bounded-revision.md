# Perform one bounded Revision Attempt

Status: ready-for-agent
Type: AFK
User stories: 51-52, 67-68, 70-71

## What to build

Add conditional LangGraph routing for one Revision Attempt after Patch Review rejects a Test Patch. The generator receives the review findings and may replace its complete-file proposal once; the revised Test Patch is validated, regenerated through Git, and reviewed again.

A second rejection must terminate the Coding Run as a review-stage Run Failure rather than entering an unbounded retry loop.

## Acceptance criteria

- [ ] A first Patch Review rejection routes the Coding Run through exactly one Revision Attempt.
- [ ] Revision receives the original task, Repository Evidence, prior proposal, canonical diff, and reviewer findings.
- [ ] Revised complete-file proposals pass through the same path and Test File validation as initial generation.
- [ ] Git derives a new canonical diff after the revised files are written.
- [ ] An accepted second review transitions the Coding Run to `awaiting_approval`.
- [ ] A rejected second review transitions the Coding Run to `failed` with failure stage `review` and a sanitized reason.
- [ ] Agent Stream events distinguish revision and second-review stages and end with one persisted terminal result.
- [ ] Graph tests cover first-pass acceptance, successful revision, second-review rejection, revision generation failure, and validation failure.

## Blocked by

- [11 - Review a Test Patch before Approval](11-review-test-patch.md)

