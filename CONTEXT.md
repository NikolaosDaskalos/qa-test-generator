# AI Codebase Copilot

An AI course capstone that demonstrates repository-grounded question answering and an agentic test-generation workflow for Python repositories hosted on GitHub.

## Language

**Repository**:
A public or private GitHub-hosted Python codebase connected to the copilot for indexing, questions, and test generation. GitLab, Bitbucket, and non-Python repositories are outside the demo scope.
_Avoid_: Project, codebase connection

**Repository Credential**:
A mandatory GitHub token used for clone, fetch, and approved non-default branch pushes. Public repositories use the same credential flow as private repositories.
_Avoid_: Optional token, anonymous connection

**Repository Session**:
A conversation and task workspace bound to exactly one Repository for its lifetime. Working with another Repository requires a new Repository Session.
_Avoid_: Search Session, chat session

**Session History**:
The persisted exchanges within a Repository Session. Each assistant exchange retains its supporting Repository Evidence citations as structured data, kept distinct from the answer text rather than embedded in it. At most the six most recent messages influence question reformulation or task planning, and no duplicate session-memory copy is maintained.
_Avoid_: Session memory blob, full-history prompt, citations rendered into message text

**Repository Evidence**:
Indexed code units retrieved only from the Repository bound to the current Repository Session. Answers, plans, generated tests, reviews, and citations must not use chunks from another Repository.
_Avoid_: User-wide retrieval, cross-repository context

**Code Chunk**:
A Python-aware text segment identified by Repository, commit SHA, and file path. Symbol extraction and line-level citations are outside the demo scope.
_Avoid_: AST symbol unit, line-level source unit

**Repository Synchronization**:
The file-level update that aligns Repository Evidence with the latest commit of the Repository's default branch. Added files are indexed, modified and renamed files are replaced, and deleted files are removed; the indexed commit advances only after all changes succeed.
_Avoid_: Full re-index, metadata-only rename

**Synchronization Request**:
A user-initiated request to run Repository Synchronization in the background and report its status or failure. Scheduled and webhook-triggered synchronization are outside the demo scope.
_Avoid_: Automatic sync, webhook sync

**External Reference**:
Web-sourced documentation or testing guidance the test generator may consult for a test framework's current syntax and best practices. It must be clearly separated from Repository Evidence and can never support claims about the Repository's code or behavior — only how tests are written. Web search is reachable solely on the test-generation path; ordinary Repository questions never reach it.
_Avoid_: Repository evidence, uncited model knowledge, web access on the repository-question path

**Request Intent**:
The classified purpose of a question submitted to a Repository Session, inferred at the single questions entry point: either a Repository question, answered by repository-grounded retrieval, or a Test-Generation Task, which starts a Coding Run. Uncertain classification falls back to a Repository question, which has no side effects.
_Avoid_: Explicit client-supplied mode flag, a separate endpoint per intent, External Research Request

**Research Intent**:
A planner-produced description of evidence to find, optionally including candidate Repository paths. Candidate paths are untrusted hints; only validated paths and retrieved Repository Evidence may enter agent context.
_Avoid_: Filesystem instruction, unrestricted file read

**Test-Generation Task**:
A free-text request to add or improve tests for code in the Repository. It may change Test Files only; changing application code is outside the demo scope.
_Avoid_: Feature task, bug-fix task

**Test File**:
An existing Python test file, or a new Python file within an existing Repository test root. Files outside the checkout, symlinks, non-Python files, source files, and newly invented test roots are not Test Files.
_Avoid_: Application file, arbitrary generated file

**Test Patch**:
A validated set of complete Test File contents proposed by a Test-Generation Task. The backend writes these files and derives the human-readable unified diff from Git.
_Avoid_: LLM-authored unified diff, application-code patch

**Patch Review**:
An evidence-based assessment that scores a Test Patch out of ten against the task, repository conventions, and retrieved code, accompanied by categorized findings. The reviewer only scores; the backend decides pass/fail against a configurable threshold (default seven) and independently hard-fails any patch that escapes the Test File boundary regardless of score. It does not execute tests or install repository dependencies.
_Avoid_: Test execution, CI validation, model-decided accept/reject, reviewer as the sole gate

**Revision Budget**:
The configurable number of opportunities (default two) for the test generator to correct a Test Patch scored below threshold by Patch Review. Exhausting the budget never fails the Coding Run: the best-scoring attempt is still escalated to human review with its score and findings, so the owner always gets to inspect and decide. The same generator agent performs both generation and revision; revision is no longer tool-free.
_Avoid_: Single fixed attempt, unlimited revision, failing the run on exhaustion, a separate revision agent

**Coding Run**:
A test-generation attempt performed in the Repository's local checkout on a temporary non-default branch. A Repository has at most one active Coding Run; concurrent requests are outside the demo scope.
_Avoid_: Concurrent run, isolated worktree

**Agent Stream**:
The synchronous server-sent event response for a Repository question or Test-Generation Task. It reports stage progress, generated content, review findings, and the final persisted result without polling or background agent execution. Its events form a closed vocabulary: Stage progress markers (classifying, planning, retrieving, researching, generating), Token chunks, and exactly one terminal event — Result for a Repository question (citations ride on it), PatchResult for a generated Test Patch, or RunFailure for a failed Coding Run. Deliberate outcomes — including insufficient evidence, an out-of-scope Test-Generation Task, or a rejected Test Patch — are normal terminal events in this vocabulary. Only unexpected transport failures (a dropped connection, an upstream crash) are surfaced as an out-of-band error frame by the SSE adapter, outside the event vocabulary.
_Avoid_: WebSocket, polling workflow, error event for a deliberate outcome

**Approval**:
The user's authorization to commit an accepted Test Patch to a new non-default branch and push that branch to the Repository remote. Approval never permits a push to the Repository's default branch.
_Avoid_: Merge, pull-request approval

**Run Failure**:
A terminal Coding Run outcome identified by the stage that failed and a sanitized reason, reserved for unexpected stage errors: generation errors, patch validation errors, Git commit errors, and Git push errors, kept distinguishable without becoming separate run statuses. A Test Patch scored below threshold is not a Run Failure — it escalates to human review.
_Avoid_: Generic failure, provider error dump, failing the run on a low review score
