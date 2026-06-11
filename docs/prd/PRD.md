# AI Codebase Copilot Backend

Status: `ready-for-agent`

## Problem Statement

Developers need a practical way to explore an unfamiliar Python Repository and generate relevant tests without manually tracing the entire codebase. General-purpose LLM answers are insufficient because they can mix model knowledge with unsupported assumptions, lose track of repository boundaries, or generate broad changes that are difficult to review.

This course project also needs to demonstrate concrete understanding of retrieval-augmented generation and bounded agentic workflows. The existing backend already supports authenticated repository cloning, Python-aware vector ingestion, hybrid retrieval, basic agent execution, and protected Git pushes, but these capabilities are not yet combined into one repository-scoped workflow.

The user needs a demo in which answers are grounded in one connected Repository, test generation is limited to Test Files, generated changes pass through Patch Review, and Approval can publish a non-default branch without permitting direct modification of the default branch.

## Solution

Build a FastAPI backend workflow for public and private Python repositories hosted on GitHub.

A user connects a Repository with a mandatory Repository Credential. The backend clones and indexes the default branch. The user creates a Repository Session permanently bound to that Repository and can then:

- Ask codebase questions answered from Repository Evidence with file citations.
- Explicitly request External References for documentation or testing guidance.
- Submit a Test-Generation Task through a bounded LangGraph workflow.
- Receive live progress through an Agent Stream.
- Review a generated Test Patch and Patch Review findings.
- Reject the patch or approve a commit and push to a new non-default branch.

Repository Synchronization keeps Repository Evidence aligned with the latest default-branch commit through file-level incremental updates rather than a full re-index.

The project remains a focused demonstration. It does not install dependencies, execute generated tests, create pull requests, support arbitrary coding tasks, or provide production concurrency guarantees.

## User Stories

1. As a user, I want to connect a public GitHub Python Repository, so that I can explore its code through the copilot.
2. As a user, I want to connect a private GitHub Python Repository, so that I can use the same workflow with non-public code.
3. As a user, I want every Repository connection to require a Repository Credential, so that cloning, fetching, and an approved branch push use one consistent authentication flow.
4. As a user, I want non-GitHub repository URLs to be rejected, so that the demo has a clear provider boundary.
5. As a user, I want repositories without a usable Python codebase to be rejected or reported as unsupported, so that the system does not imply multi-language support.
6. As a user, I want Repository cloning and initial indexing to run in the background, so that the connection request does not remain blocked.
7. As a user, I want to see Repository processing status, so that I know whether cloning, indexing, readiness, or failure is current.
8. As a user, I want Repository failures to contain sanitized reasons, so that I can understand failures without exposing credentials.
9. As a user, I want the backend to record the indexed default-branch commit, so that Repository Evidence has a known source snapshot.
10. As a user, I want to request Repository Synchronization manually, so that I control when the index follows upstream changes.
11. As a user, I want synchronization to fetch the latest default branch, so that new upstream commits can become available for questions and tasks.
12. As a user, I want newly added Python files to be indexed incrementally, so that synchronization does not rebuild unrelated vectors.
13. As a user, I want modified Python files to have their old Code Chunks replaced, so that stale content is not retrieved.
14. As a user, I want deleted Python files removed from Repository Evidence, so that answers cannot cite code that no longer exists.
15. As a user, I want renamed Python files re-indexed under their new path, so that file citations remain correct.
16. As a user, I want the indexed commit to advance only after synchronization succeeds, so that the stored snapshot never claims a partially updated index.
17. As a user, I want synchronization status and failure information, so that I can distinguish successful, active, and failed updates.
18. As a user, I want to create a Repository Session for one Repository, so that every conversation has an explicit evidence boundary.
19. As a user, I want a Repository Session to remain bound to its original Repository, so that later messages cannot accidentally query another Repository.
20. As a user, I want to create a new Repository Session when changing repositories, so that each session remains coherent.
21. As a user, I want Session History persisted as individual exchanges, so that conversations can continue without a duplicate memory blob.
22. As a user, I want only recent Session History used for reformulation and planning, so that prompts remain bounded.
23. As a user, I want to ask where a behavior is implemented, so that I can locate relevant files quickly.
24. As a user, I want to ask how components interact, so that I can understand repository architecture.
25. As a user, I want follow-up questions to account for recent conversation context, so that I do not have to repeat the subject.
26. As a user, I want every codebase answer grounded only in the Repository Session's Repository Evidence, so that claims do not come from another connected Repository.
27. As a user, I want file citations with codebase answers, so that I can inspect the supporting source.
28. As a user, I want the system to state when Repository Evidence is insufficient, so that uncertainty is visible instead of hidden by model guesses.
29. As a user, I want ordinary repository questions to avoid web search, so that external information does not contaminate repository claims.
30. As a user, I want to request documentation or testing best practices explicitly, so that external guidance is available when useful.
31. As a user, I want Repository sources and External References shown separately, so that I can distinguish codebase facts from general guidance.
32. As a user, I want question progress and answer tokens streamed through an Agent Stream, so that the interface provides immediate feedback.
33. As a user, I want to submit a free-text Test-Generation Task, so that I can describe the code behavior that needs tests.
34. As a user, I want Test-Generation Tasks limited to adding or improving tests, so that the demo does not silently become a general code-editing agent.
35. As a user, I want the planner to produce Research Intents, so that retrieval targets definitions, callers, related tests, configuration, and conventions.
36. As a user, I want planner-suggested paths treated as untrusted hints, so that the LLM cannot read arbitrary filesystem locations.
37. As a user, I want test generation to use only validated Repository Evidence, so that generated tests reflect the connected codebase.
38. As a user, I want the generator to return complete Test File contents, so that the backend does not depend on an LLM producing a perfectly applicable unified diff.
39. As a user, I want the backend to derive the unified diff with Git, so that the displayed patch accurately reflects written changes.
40. As a user, I want existing Test Files to be eligible for modification, so that the agent can improve current coverage.
41. As a user, I want new Python Test Files allowed only under an existing test root, so that the agent follows the Repository's established structure.
42. As a user, I want paths outside the checkout rejected, so that a generated patch cannot escape the Repository.
43. As a user, I want symlink targets rejected, so that path validation cannot be bypassed.
44. As a user, I want non-Python files rejected from a Test Patch, so that the demo remains within its Python scope.
45. As a user, I want application and source files rejected from a Test Patch, so that test generation cannot alter production behavior.
46. As a user, I want invented test roots rejected, so that the agent does not impose a new project structure.
47. As a user, I want Patch Review to verify task alignment, so that the patch addresses the requested testing goal.
48. As a user, I want Patch Review to check Repository conventions and visible imports, so that generated tests resemble existing tests.
49. As a user, I want Patch Review to detect unrelated changes, so that the proposal remains narrowly scoped.
50. As a user, I want Patch Review to verify that only Test Files changed, so that the test-only boundary is enforced twice.
51. As a user, I want one Revision Attempt after Patch Review rejects a patch, so that the workflow demonstrates conditional agent routing.
52. As a user, I want a second Patch Review rejection to fail the Coding Run, so that revisions cannot loop indefinitely.
53. As a user, I want Coding Run stages streamed in real time, so that planning, retrieval, generation, review, and completion are visible.
54. As a user, I want reviewer findings and the final diff included in the Agent Stream, so that I can make an informed approval decision.
55. As a user, I want the completed Coding Run persisted, so that its state, patch, review, and failures can be inspected after streaming ends.
56. As a user, I want only one active Coding Run per Repository, so that the shared checkout cannot be mutated by overlapping demo requests.
57. As a user, I want a disconnected Agent Stream to cancel its Coding Run, so that abandoned generation does not leave unexplained changes.
58. As a user, I want cancellation and failures to discard unapproved changes, so that the shared checkout returns to a known state.
59. As a user, I want a reviewed Test Patch to wait for explicit Approval, so that no branch is pushed automatically.
60. As a user, I want to reject a reviewed Test Patch, so that unwanted changes are removed without publishing them.
61. As a user, I want Approval to commit the Test Patch on a uniquely named non-default branch, so that generated work remains isolated from the default branch.
62. As a user, I want Approval to push the generated branch using the Repository Credential, so that the demo completes a real Git workflow.
63. As a user, I want pushes to the Repository's default branch rejected, so that Approval cannot directly modify `main`, `master`, or another configured default.
64. As a user, I want the local checkout restored to the indexed default-branch commit after rejection, failure, or successful push, so that later questions and tasks start from the indexed snapshot.
65. As a user, I want the local temporary branch removed after cleanup, so that abandoned local branches do not accumulate.
66. As a user, I want the successfully pushed branch to remain on GitHub, so that I can inspect or manually create a pull request.
67. As a user, I want Run Failure to identify whether review, generation, validation, commit, or push failed, so that failures are actionable.
68. As a user, I want Run Failure reasons sanitized, so that raw provider output and Repository Credentials are not exposed.
69. As a course evaluator, I want repository-scoped hybrid retrieval demonstrated, so that the project shows practical RAG understanding.
70. As a course evaluator, I want explicit LangGraph nodes and conditional routing demonstrated, so that the project shows agentic workflow understanding.
71. As a course evaluator, I want bounded revision and human Approval demonstrated, so that the workflow remains controlled and explainable.
72. As a course evaluator, I want live Agent Stream events demonstrated, so that long LLM operations provide visible progress.
73. As a course evaluator, I want incremental Repository Synchronization demonstrated, so that vector lifecycle management is visible beyond initial ingestion.
74. As a course evaluator, I want unsupported production concerns documented as out of scope, so that the demo remains focused on course objectives.

## Implementation Decisions

- The backend supports public and private Python repositories hosted on GitHub only.
- A Repository Credential is mandatory for every Repository and is used through non-interactive Git authentication for clone, fetch, and push.
- Existing credential encryption and sanitized Git error handling remain the authentication boundary.
- Repository registration schedules clone and initial indexing as a FastAPI background task.
- Repository Synchronization is manually triggered and also runs as a FastAPI background task.
- The Repository model records the commit SHA represented by Repository Evidence.
- Synchronization compares the indexed commit with the latest default-branch commit using Git rename detection and processes changes at file granularity.
- Added files are indexed, modified files are deleted and re-indexed, deleted files are removed, and renamed files are removed under the old path and indexed under the new path.
- The indexed commit SHA changes only after all vector operations complete successfully.
- Repository status exposes background processing and synchronization progress plus sanitized failure information.
- Existing Python-aware recursive splitting remains the Code Chunk strategy.
- Every Code Chunk stores Repository identity, commit SHA, source path, and parent document identity.
- Weaviate tenancy remains user-scoped, while every retrieval query additionally filters by Repository identity.
- File-level citations are required; AST symbol units and line-level citations are not required.
- Hybrid BM25 and embedding retrieval remains the retrieval method.
- Repository Session replaces Search Session as the canonical domain concept.
- A Repository Session requires a Repository identity at creation and cannot be reassigned.
- Session History is represented by persisted exchanges; the duplicate serialized memory field is removed.
- At most six recent Session History messages are supplied to reformulation and planning.
- Repository questions use Repository Evidence exclusively for claims about code and behavior.
- Insufficient evidence produces an explicit limitation response rather than an unsupported answer.
- Tavily is unavailable to normal repository questions and may be invoked only for an explicit External Research Request.
- Responses separate Repository sources from External References.
- Questions and Test-Generation Tasks use synchronous server-sent events.
- Agent Stream events cover stage progress, generated content, citations or reviewer findings, and the final persisted result.
- Agent workflows do not use polling, WebSockets, or background execution.
- Client disconnect during a Coding Run cancels processing, records failure, and triggers checkout cleanup.
- Test generation is the only coding task supported.
- The LangGraph workflow follows this bounded state progression:

  ```text
  plan
    -> retrieve
    -> generate
    -> review
    -> revise once when rejected
    -> review
    -> awaiting approval or failed
  ```

- Planner output contains Research Intents and optional candidate paths, not unrestricted file-read instructions.
- Candidate paths are normalized, confined to the Repository checkout, and verified before use.
- Retrieval determines the actual Repository Evidence supplied to generator and reviewer nodes.
- The generator returns structured complete-file proposals rather than unified diff text.
- The backend validates and writes proposed Test Files, then obtains the canonical unified diff from Git.
- Existing recognized Python Test Files may be modified.
- New Python Test Files may be created only within an existing `tests` or `test` root.
- Path escape, symlink, non-Python, source-file, and invented-test-root proposals are rejected before writing.
- Patch Review assesses task satisfaction, consistency with retrieved code and existing tests, visible import validity, unrelated modifications, and the Test File boundary.
- Patch Review does not execute tests, install dependencies, or claim runtime correctness.
- Exactly one Revision Attempt is allowed. A second review rejection terminates the Coding Run.
- One shared local checkout is used instead of Git worktrees.
- At most one active Coding Run is permitted per Repository; production-grade concurrency control is not required.
- Before generation, the checkout is restored to the indexed commit and a unique non-default temporary branch is created.
- Rejection, cancellation, and failure discard unapproved changes, restore the indexed commit, and remove the local temporary branch.
- Approval is available only from the `awaiting_approval` state.
- Approval commits and pushes the current generated branch.
- Existing default-branch push protection remains mandatory and fails closed when branch detection is unavailable.
- After successful push, the local checkout returns to the indexed commit and removes the local generated branch.
- The pushed remote branch is retained; pull-request creation is left to the user.
- Coding Run states are `queued`, `planning`, `retrieving`, `generating`, `reviewing`, `awaiting_approval`, `approved`, `rejected`, and `failed`.
- Run Failure uses one terminal status with a structured stage and sanitized reason.
- Failure stages are `review`, `generation`, `validation`, `git_commit`, and `git_push`.
- Repository synchronization endpoints expose status through normal JSON responses.
- Question and task endpoints return server-sent event responses.
- Run lookup and patch lookup endpoints expose persisted outcomes.
- Approval and rejection endpoints are ordinary synchronous requests.

## Testing Decisions

- Tests assert externally visible behavior, persisted state, emitted Agent Stream events, Git effects, and vector-store interactions. They do not assert prompt wording, private helper calls, or LangGraph's internal implementation details.
- FastAPI route tests use `TestClient` and dependency overrides, following the existing repository route tests. They cover authentication and ownership, Repository Session binding, background synchronization scheduling, SSE content types and terminal events, run lookup, Approval, rejection, and sanitized errors.
- SSE tests consume complete test streams and assert ordered stage events plus the final result. Token chunk boundaries are not treated as stable behavior.
- Repository service tests use fake stores, fake Git commands, and fake ingestion resources, following existing service tests. They cover GitHub-only validation, initial processing, incremental synchronization status, commit advancement, and failure preservation.
- Incremental synchronization tests cover add, modify, delete, rename, no-change, fetch failure, diff failure, vector-write failure, and the rule that indexed commit SHA advances only on full success.
- Ingestor tests use fake Weaviate resources, following existing RAG ingestion tests. They cover Code Chunk metadata, file-level replacement, deletion by source or parent identity, and user-tenant isolation.
- Retriever tests use fake vector-store resources, following existing retrieval tests. They verify that Repository identity filters are always applied and that results from another Repository cannot enter Repository Evidence.
- RAG pipeline tests use fake model, retriever, and chain dependencies, following existing pipeline construction tests. They cover repository-scoped construction, recent Session History, insufficient-evidence responses, file citations, and explicit External Research Requests.
- LangGraph tests use deterministic fake planner, retriever, generator, reviewer, and event sinks. They cover the accepted path, one Revision Attempt, second-review failure, generation failure, validation failure, disconnect cancellation, and event ordering.
- LangGraph tests treat node outputs and state transitions as contracts. They do not call external LLM or Tavily services.
- Patch validation tests operate on temporary Repository checkouts and cover existing Test Files, new files in existing test roots, path traversal, absolute paths, symlinks, non-Python files, source files, and invented test roots.
- Git command tests mock subprocess execution, following existing Git tests. They cover checkout restoration, temporary branch creation, diff generation, commit, push, default-branch rejection, token redaction, and local branch cleanup.
- Coding Run service tests cover every permitted and rejected state transition.
- Failure tests verify structured failure stages and sanitized user-visible reasons without requiring exact provider error text.
- Persistence tests follow existing store tests and cover Repository indexed commit state, Repository Session ownership and binding, Session History ordering, Coding Run state, Test Patch persistence, Patch Review findings, and Run Failure fields.
- Model and migration tests verify required foreign keys, cascade behavior, uniqueness constraints, enum values, and removal of duplicate session memory.
- Tests do not clone real repositories, push real branches, install target Repository dependencies, execute generated tests, call OpenAI, call Tavily, or require a live Weaviate instance.
- A small manually operated end-to-end demo remains appropriate for course presentation: connect a controlled GitHub Repository, ask a cited question, generate a Test Patch, reject one run, approve another, and verify the non-default remote branch.

## Out of Scope

- GitLab, Bitbucket, self-hosted Git providers, and local-only repositories.
- Languages other than Python.
- General feature implementation, bug fixing, refactoring, or application-code modification.
- Test execution, dependency installation, virtual-environment creation, coverage analysis, linting, and type checking inside connected repositories.
- Runtime verification of generated tests.
- Automatic pull-request creation or provider-specific GitHub API integration.
- GitHub Actions creation, management, or check-status integration.
- Automatic synchronization through schedules, polling, webhooks, or push events.
- GraphRAG, call graphs, import graphs, and symbol-level relationship indexing.
- AST unit-per-symbol chunking and line-level citations.
- Full re-indexing during normal Repository Synchronization.
- Metadata-only rename optimization.
- Cross-repository questions or tasks within one Repository Session.
- Automatic web search for ordinary repository questions.
- Unrestricted shell commands or unrestricted LLM filesystem access.
- Arbitrary unified diffs generated directly by the LLM.
- Multiple simultaneous Coding Runs for one Repository.
- Git worktrees and production-grade checkout isolation.
- Multi-process locking, distributed workers, queues, retries, and crash recovery guarantees.
- Polling-based agent workflows and WebSockets.
- Direct pushes to the Repository's default branch.
- Automatic merging or remote generated-branch deletion.
- Production security, scalability, observability, cost controls, and multi-region deployment beyond what is necessary for the course demo.

## Further Notes

- The purpose is to demonstrate RAG, hybrid retrieval, repository-scoped evidence, LangGraph state and routing, bounded agent revision, streaming feedback, human Approval, and Git integration.
- Existing repository, Git, RAG, Weaviate, FastAPI, authentication, and persistence patterns should be extended rather than replaced.
- The shared checkout design is intentionally simple because concurrent requests are outside scope. Cleanup behavior is still required so sequential demo runs remain deterministic.
- Patch Review communicates evidence-based confidence but must not imply that generated tests pass, because execution is explicitly excluded.
- A successfully pushed generated branch is the terminal integration artifact. The user may create a pull request manually through GitHub.
- The implementation plan and domain glossary remain the controlling references for terminology and scope.
