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
The persisted exchanges within a Repository Session. At most the six most recent messages influence question reformulation or task planning, and no duplicate session-memory copy is maintained.
_Avoid_: Session memory blob, full-history prompt

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
Web-sourced documentation or testing guidance used only to supplement general recommendations. It must be clearly separated from Repository Evidence and cannot support claims about the Repository's code or behavior.
_Avoid_: Repository evidence, uncited model knowledge

**External Research Request**:
An explicit user request for documentation, best practices, or other external guidance. Only such a request may use web search, and its External References must be presented separately from Repository sources.
_Avoid_: Automatic web search, implicit external lookup

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
An evidence-based assessment of whether a Test Patch matches the task, repository conventions, and retrieved code. It does not execute tests or install repository dependencies.
_Avoid_: Test execution, CI validation

**Revision Attempt**:
The single opportunity for the test generator to correct a Test Patch rejected by Patch Review. A second rejection fails the Coding Run and prevents Approval.
_Avoid_: Retry loop, unlimited revision

**Coding Run**:
A test-generation attempt performed in the Repository's local checkout on a temporary non-default branch. A Repository has at most one active Coding Run; concurrent requests are outside the demo scope.
_Avoid_: Concurrent run, isolated worktree

**Agent Stream**:
The synchronous server-sent event response for a Repository question or Test-Generation Task. It reports stage progress, generated content, review findings, and the final persisted result without polling or background agent execution. Its events form a closed vocabulary (Stage, Token, Sources, Citations, Result). Deliberate outcomes — including failures such as insufficient evidence or a rejected Test Patch — are normal terminal events in this vocabulary. Only unexpected transport failures (a dropped connection, an upstream crash) are surfaced as an out-of-band error frame by the SSE adapter, outside the event vocabulary.
_Avoid_: WebSocket, polling workflow, error event for a deliberate outcome

**Approval**:
The user's authorization to commit an accepted Test Patch to a new non-default branch and push that branch to the Repository remote. Approval never permits a push to the Repository's default branch.
_Avoid_: Merge, pull-request approval

**Run Failure**:
A terminal Coding Run outcome identified by the stage that failed and a sanitized reason. Review rejection, generation errors, patch validation errors, Git commit errors, and Git push errors remain distinguishable without becoming separate run statuses.
_Avoid_: Generic failure, provider error dump
