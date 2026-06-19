# AI Codebase Copilot

An AI course capstone that demonstrates repository-grounded question answering and an agentic code-generation workflow for Python repositories hosted on GitHub.

## Language

**Repository**:
A public or private GitHub-hosted Python codebase connected to the copilot for indexing, questions, and code generation. GitLab, Bitbucket, and non-Python repositories are outside the demo scope.
_Avoid_: Project, codebase connection

**Repository Credential**:
A mandatory GitHub token used for clone, fetch, and approved non-default branch pushes. Public repositories use the same credential flow as private repositories.
_Avoid_: Optional token, anonymous connection

**Repository Session**:
A conversation and task workspace bound to exactly one Repository for its lifetime. Working with another Repository requires a new Repository Session.
_Avoid_: Search Session, chat session

**Session History**:
The complete persisted exchanges within a Repository Session, available for chronological display. Each assistant exchange retains citations to its supporting Repository Documents as structured data kept distinct from the answer text; at most the ten most recent messages influence question reformulation or task planning, and no duplicate session-memory copy is maintained.
_Avoid_: Session memory blob, full-history prompt, citations rendered into message text

**Repository Document**:
The indexed representation of a file from the Repository bound to the current Repository Session. Answers, plans, generated tests, reviews, and citations must not use Repository Documents or their Code Chunks from another Repository.
_Avoid_: Repository Evidence, Repository File, user-wide retrieval, cross-repository context

**Code Chunk**:
A Python-aware text segment identified by Repository, commit SHA, and file path. Symbol extraction and line-level citations are outside the demo scope.
_Avoid_: AST symbol unit, line-level source unit

**Repository Synchronization**:
The file-level update that aligns Repository Documents with the latest commit of the Repository's default branch. Added files are indexed, modified and renamed files are replaced, and deleted files are removed; the indexed commit advances only after all changes succeed.
_Avoid_: Full re-index, metadata-only rename

**Synchronization Request**:
A user-initiated request to run Repository Synchronization in the background and report its status or failure. Scheduled and webhook-triggered synchronization are outside the demo scope.
_Avoid_: Automatic sync, webhook sync

**External Reference**:
Web-sourced documentation or testing guidance the code generator may consult for a test framework's current syntax and best practices. It must be clearly separated from Repository Documents and can never support claims about the Repository's code or behavior — only how tests are written. Web search is reachable solely on the code-generation path; ordinary Repository questions never reach it.
_Avoid_: Repository Document, uncited model knowledge, web access on the repository-question path

**Request Intent**:
The classified purpose of a question submitted to a Repository Session, inferred at the single questions entry point: either a Repository question, answered by repository-grounded retrieval, or a Code Generation Task, which starts a Coding Run. Uncertain classification falls back to a Repository question, which has no side effects.
_Avoid_: Explicit client-supplied mode flag, a separate endpoint per intent, External Research Request

**Retrieval Request**:
A planner-produced description of Repository content to retrieve, optionally including candidate Repository paths. Candidate paths are untrusted hints; only validated paths and retrieved Repository content may enter agent context.
_Avoid_: Research Intent, Research Document, filesystem instruction, unrestricted file read

**Code Generation Task**:
A free-text request to add or improve tests for code in the Repository. It may change Test Files only; changing application code is outside the demo scope.
_Avoid_: Test-Generation Task, feature task, bug-fix task

**Test File**:
An existing Python test file, or a new Python file within an existing Repository test root. Files outside the checkout, symlinks, non-Python files, source files, and newly invented test roots are not Test Files.
_Avoid_: Application file, arbitrary generated file

**Test Patch**:
A validated set of complete Test File contents proposed by a Code Generation Task. The backend writes these files and derives the human-readable unified diff from Git.
_Avoid_: LLM-authored unified diff, application-code patch

**Code Reviewer**:
The agent that statically assesses a Test Patch against the Code Generation Task, repository conventions, and retrieved Repository Documents. It does not execute tests or decide whether the patch passes.
_Avoid_: Patch Reviewer, test runner, approval gate

**Patch Review**:
A static assessment grounded in Repository Documents, produced by the Code Reviewer, that scores a Test Patch out of ten against the task and repository conventions and includes categorized findings. The Code Reviewer only scores; the backend decides pass/fail against a configurable threshold (default seven) and independently hard-fails any patch that escapes the Test File boundary regardless of score.
_Avoid_: Test execution, CI validation, model-decided accept/reject, reviewer as the sole gate

**Generation Retries**:
The configurable number of opportunities (default two) for the code generator to correct a Test Patch scored below threshold by Patch Review. Exhausting the retries never fails the Coding Run: the best-scoring attempt is still escalated to human review with its score and findings, so the owner always gets to inspect and decide. The same generator agent performs both generation and revision; revision is not tool-free.
_Avoid_: Revision Budget, Review Retries, single fixed attempt, unlimited revision, failing the run on exhaustion, a separate revision agent

**Coding Run**:
A code-generation attempt performed in the Repository's local checkout on a temporary non-default branch. A Repository has at most one active Coding Run; concurrent requests are outside the demo scope.
_Avoid_: Concurrent run, isolated worktree

**Agent Stream**:
The synchronous server-sent event response for a Repository question or Code Generation Task. It reports stage progress, generated content, review findings, and the final persisted result without polling or background agent execution. Its events form a closed vocabulary: Stage progress markers (classifying, planning, retrieving, researching, generating, reviewing, revising, re_reviewing), Token chunks, a RunStarted marker identifying the Coding Run, and exactly one terminal event — Result for a Repository question (citations ride on it), ReviewResult for a generated Test Patch escalated to the owner's decision, RunApproved or RunRejected for the owner's resolved decision, or RunFailure for a failed Coding Run. The internal PatchResult record is built into graph state but never emitted on the stream; the generated patch and files are read afterward from the Coding Run's persisted state. Deliberate outcomes — including insufficient Repository Documents, an out-of-scope Code Generation Task, or a rejected Test Patch — are normal terminal events in this vocabulary. Only unexpected transport failures (a dropped connection, an upstream crash) are surfaced as an out-of-band error frame by the SSE adapter, outside the event vocabulary.
_Avoid_: WebSocket, polling workflow, error event for a deliberate outcome

**Approval**:
The user's authorization to commit an accepted Test Patch to a new non-default branch and push that branch to the Repository remote. Approval never permits a push to the Repository's default branch.
_Avoid_: Merge, pull-request approval

**Run Failure**:
A terminal Coding Run outcome identified by the stage that failed and a sanitized reason, reserved for unexpected stage errors: generation errors, patch validation errors, Git commit errors, and Git push errors, kept distinguishable without becoming separate run statuses. A Test Patch scored below threshold is not a Run Failure — it escalates to human review.
_Avoid_: Generic failure, provider error dump, failing the run on a low review score
