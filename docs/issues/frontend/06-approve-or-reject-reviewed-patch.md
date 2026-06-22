# Approve or reject a reviewed Test Patch (human-in-the-loop resume)

Status: completed
Type: AFK
User stories: frontend bare-minimum copilot

## What to build

Close the human-in-the-loop loop from the chat. When a reviewed Test Patch is awaiting the owner's
decision, the chat presents inline Approve and Reject controls, with an optional feedback field on
reject. Submitting a decision resumes the same paused run through the same session questions
endpoint — sending a decision payload rather than a question — and streams the outcome back through
the existing SSE reader.

The decision turn ends in one of two terminal frames: an approval that reports the pushed
non-default branch and the approved canonical diff, or a rejection that reports the findings and
discards the patch. The disclaimer is restated on both. After a decision resolves, the controls are
no longer offered for that run.

## Acceptance criteria

- [x] A run awaiting decision shows inline Approve and Reject controls, with an optional feedback field for reject.
- [x] Submitting a decision posts the decision payload to the session questions endpoint and streams the result through the existing SSE reader.
- [x] An approval renders the pushed branch name and approved canonical diff; a rejection renders the findings.
- [x] The disclaimer is shown on both approval and rejection outcomes.
- [x] Once a decision resolves, the approve/reject controls are no longer offered for that run.

## Blocked by

- [05 - Run a Test-Generation Task and render the reviewed Test Patch](05-run-test-generation-and-render-patch.md)
