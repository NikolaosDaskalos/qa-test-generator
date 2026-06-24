# AI Codebase Copilot

An AI course capstone that demonstrates repository-grounded question answering and an agentic code-generation workflow for Python repositories hosted on GitHub.

## Language

**Repository**:
A public or private GitHub-hosted Python codebase connected to the copilot for indexing, questions, and code generation. GitLab, Bitbucket, and non-Python repositories are outside the demo scope.
_Avoid_: Project, codebase connection

**Repository Credential**:
A mandatory GitHub token used for clone, fetch, approved non-default branch pushes, and opening the Pull Request that proposes an approved branch. Public repositories use the same credential flow as private repositories. The same credential authenticates both the Git protocol operations and the GitHub API operations; opening a Pull Request additionally requires the token to carry pull-request write permission.
_Avoid_: Optional token, anonymous connection, a separate API credential

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
A user-initiated request to run Repository Synchronization in the background and report its status or failure. Scheduled and webhook-triggered synchronization are outside the demo scope. The system may *notice* that a Synchronization Request is worthwhile (see Sync Availability) but never raises one on the user's behalf.
_Avoid_: Automatic sync, webhook sync

**Sync Availability**:
A read-only background signal that running a Synchronization Request would do work, because the Repository's remote default-branch head has advanced beyond its indexed commit. It is observed by polling the remote head with `git ls-remote` — which never opens the local checkout, so observing it is not a Checkout Operation — and derived by comparing the last observed upstream head against the indexed commit. Observing Sync Availability never runs Repository Synchronization, never mutates the checkout or Repository Documents, and never changes Repository status or `failed_reason`; a failed poll leaves the last known signal untouched. It only surfaces a "sync now" affordance for the owner to act on.
_Avoid_: Automatic synchronization, polling-triggered sync, a Checkout Operation, advancing the indexed commit, flipping Repository status on a failed poll

**Checkout Operation**:
Any operation that mutates a Repository's single local checkout — cloning and indexing, Repository Synchronization, or a Coding Run. At most one Checkout Operation is in progress for a Repository at a time; a concurrent request for the same Repository is rejected, while a Checkout Operation on a different Repository proceeds independently. Repository questions read only indexed Repository Documents, never engage this exclusion, and stay available while a Checkout Operation runs. This generalizes the single-active-Coding-Run rule to the whole checkout, and is distinct from the Repository's readiness for questions, which a running Coding Run leaves intact.
_Avoid_: Per-operation locks that let two writers share a checkout, serializing Repository questions, blocking a different Repository, treating the question path as a Checkout Operation

**External Reference**:
Web-sourced documentation or testing guidance the code generator may consult for a test framework's current syntax and best practices. It must be clearly separated from Repository Documents and can never support claims about the Repository's code or behavior — only how tests are written. Web search is reachable solely on the code-generation path; ordinary Repository questions never reach it.
_Avoid_: Repository Document, uncited model knowledge, web access on the repository-question path

**Request Intent**:
The classified purpose of a question submitted to a Repository Session, inferred at the single questions entry point: either a Repository question, answered by repository-grounded retrieval, or a Code Generation Task, which starts a Coding Run. Uncertain classification falls back to a Repository question, which has no side effects.
_Avoid_: Explicit client-supplied mode flag, a separate endpoint per intent, External Research Request

**Question Shape**:
The structural classification of a Repository question — `simple`, `independent`, or `chained` — inferred on the repository-question branch (the `analyzing` step) to select a retrieval strategy. A `simple` question is a single focused ask answered with multi-query plus RAG-fusion retrieval; an `independent` question bundles several unrelated sub-questions answered in parallel (parallel decomposition) and recombined; a `chained` question is a sequence where each sub-question depends on the previous answer (recursive, IRCoT-style decomposition). It is distinct from Request Intent: Request Intent chooses the branch (repository question vs Code Generation Task), while Question Shape is read only after a question has already been routed to the repository-question branch. Uncertain classification falls back to `simple`, which is read-only and side-effect-free.
_Avoid_: a client-supplied complexity flag, conflating it with Request Intent, "left panel/right panel", "multiple questions" for the independent shape, web access (the repository-question branch never reaches the web)

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

**Patch Execution**:
The dynamic counterpart to Patch Review: the Test Files in a Test Patch are run in an isolated, network-less sandbox against a disposable copy of the checkout, before the patch is eligible for review. Only the patch's own Test Files are run, so the Repository's pre-existing or flaky tests never gate the patch; passing means those files collect and succeed. A failing execution returns the patch to the code generator with the captured failure output, up to a bounded number of Execution Attempts kept separate from Generation Retries; exhausting them does not fail the Coding Run — the patch proceeds to Patch Review flagged as not passing, so the owner still inspects and decides. When the tests cannot be run at all (the sandbox is unavailable or the environment cannot be provisioned), the patch proceeds to review flagged as not executed, rather than failing the run or spending an Execution Attempt. Untrusted generated code never receives the Repository Credential or any other secret, network access, or the real checkout.
_Avoid_: running the whole repository suite, executing tests as part of Patch Review, sharing the Generation Retries budget, failing the run on a test failure or a missing sandbox, the real checkout or live network inside the sandbox

**Execution Attempts**:
The bounded number of opportunities (default four) for the code generator to correct a Test Patch whose Test Files fail Patch Execution, distinct from Generation Retries, which count revisions driven by a below-threshold Patch Review score. The two budgets are spent independently; only a run whose tests actually executed and failed spends an Execution Attempt.
_Avoid_: Generation Retries, a shared attempt budget, spending an attempt on a sandbox or provisioning failure

**Code Reviewer**:
The agent that statically assesses a Test Patch against the Code Generation Task, repository conventions, and retrieved Repository Documents. It does not execute tests or decide whether the patch passes; running the Test Files is Patch Execution's concern.
_Avoid_: Patch Reviewer, test runner, approval gate

**Patch Review**:
A static assessment grounded in Repository Documents, produced by the Code Reviewer, that scores a Test Patch out of ten against the task and repository conventions and includes categorized findings. The Code Reviewer only scores; the backend decides pass/fail against a configurable threshold (default seven) and independently hard-fails any patch that escapes the Test File boundary regardless of score.
_Avoid_: executing tests within Patch Review (that is Patch Execution), CI validation, model-decided accept/reject, reviewer as the sole gate

**Generation Retries**:
The configurable number of opportunities (default two) for the code generator to correct a Test Patch scored below threshold by Patch Review. Exhausting the retries never fails the Coding Run: the best-scoring attempt is still escalated to human review with its score and findings, so the owner always gets to inspect and decide. The same generator agent performs both generation and revision; revision is not tool-free.
_Avoid_: Revision Budget, Review Retries, single fixed attempt, unlimited revision, failing the run on exhaustion, a separate revision agent

**Coding Run**:
A code-generation attempt performed in the Repository's local checkout on a temporary non-default branch. A Repository has at most one active Coding Run; concurrent requests are outside the demo scope.
_Avoid_: Concurrent run, isolated worktree

**Agent Stream**:
The synchronous server-sent event response for a Repository question or Code Generation Task. It reports stage progress, generated content, review findings, and the final persisted result without polling or background agent execution. Its events form a closed vocabulary: Stage progress markers (classifying, analyzing, planning, retrieving, decomposing, researching, generating, synthesizing, executing, reviewing, revising, re_reviewing), Token chunks, a RunStarted marker identifying the Coding Run, and exactly one terminal event — Result for a Repository question (citations ride on it), ReviewResult for a generated Test Patch escalated to the owner's decision, RunApproved or RunRejected for the owner's resolved decision, or RunFailure for a failed Coding Run. The internal PatchResult record is built into graph state but never emitted on the stream; the generated patch and files are read afterward from the Coding Run's persisted state. Deliberate outcomes — including insufficient Repository Documents, an out-of-scope Code Generation Task, or a rejected Test Patch — are normal terminal events in this vocabulary. Only unexpected transport failures (a dropped connection, an upstream crash) are surfaced as an out-of-band error frame by the SSE adapter, outside the event vocabulary.
_Avoid_: WebSocket, polling workflow, error event for a deliberate outcome

**Approval**:
The user's authorization to commit an accepted Test Patch to a new non-default branch, push that branch to the Repository remote, and open a Pull Request from it into the Repository's default branch. Approval never permits a push to, or a merge into, the Repository's default branch — it only proposes one for the owner to merge on GitHub.
_Avoid_: Merge, backend-side merge, direct default-branch write

**Pull Request**:
The GitHub pull request the backend opens from an approved generated branch into the Repository's default branch. Its body carries the Patch Review — the score and the categorized findings — so the owner inspects the proposed Test Files and the assessment together on GitHub. The backend opens it through the GitHub API using the Repository Credential; whether and when to merge it is the owner's decision on GitHub and is outside the demo scope. Pull-request creation runs only on the Approval path, after the branch is successfully pushed.
_Avoid_: Auto-merge, backend-side merge, gh-CLI invocation, a pull request on the question or rejection path

**Run Failure**:
A terminal Coding Run outcome identified by the stage that failed and a sanitized reason, reserved for unexpected stage errors: generation errors, patch validation errors, Git commit errors, Git push errors, and pull-request creation errors, kept distinguishable without becoming separate run statuses. A pull-request creation error is distinct from a push error: the generated branch is already on the remote, so the failure reports that the branch exists but the Pull Request could not be opened. A Test Patch scored below threshold is not a Run Failure — it escalates to human review.
_Avoid_: Generic failure, provider error dump, failing the run on a low review score
