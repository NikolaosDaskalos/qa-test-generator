# Run the complete course demonstration

Status: ready-for-human
Type: HITL
User stories: 69-74

## What to build

Validate the completed backend through a manually operated end-to-end course demonstration using a controlled GitHub Python Repository and real configured integrations. The demonstration must show repository-scoped RAG, incremental Repository Synchronization, the bounded LangGraph workflow, live Agent Stream events, human rejection, and Approval to a non-default remote branch.

Document the observed results and retain the stated out-of-scope boundaries without expanding the implementation into test execution, pull-request creation, production concurrency, or other excluded concerns.

## Acceptance criteria

- [ ] Connect a controlled GitHub Python Repository using a Repository Credential and observe background clone, indexing, and ready status.
- [ ] Ask a Repository question and verify the streamed answer is grounded in that Repository with inspectable file citations.
- [ ] Change the controlled Repository's default branch, request synchronization, and verify file-level Repository Evidence and indexed commit advancement.
- [ ] Run a Test-Generation Task and observe planning, retrieval, generation, Patch Review, optional Revision Attempt, findings, and final diff in the Agent Stream.
- [ ] Reject one reviewed Test Patch and verify local checkout and branch cleanup without a remote push.
- [ ] Approve another reviewed Test Patch and verify a unique non-default branch is pushed while the default branch remains unchanged.
- [ ] Verify persisted Repository Session, Session History, Coding Run, Test Patch, Patch Review, Approval or rejection, and Run Failure information is inspectable.
- [ ] Record that target Repository tests were not executed and that pull-request creation, dependency installation, arbitrary coding, and production concurrency remain out of scope.

## Blocked by

- [03 - Incrementally synchronize Repository Evidence](03-incrementally-synchronize-repository-evidence.md)
- [07 - Add explicit External Research Requests](07-support-explicit-external-research.md)
- [12 - Perform one bounded Revision Attempt](12-perform-bounded-revision.md)
- [14 - Reject and discard a reviewed Test Patch](14-reject-reviewed-test-patch.md)
- [15 - Approve and push a protected generated branch](15-approve-and-push-generated-branch.md)
