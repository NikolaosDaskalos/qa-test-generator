# AI Codebase Copilot

Status: `ready-for-agent`

## Problem Statement

Developers need a practical way to explore an unfamiliar Python Repository and generate relevant tests without manually tracing the entire codebase. General-purpose LLM answers are insufficient because they can mix model knowledge with unsupported assumptions, lose track of repository boundaries, or generate broad changes that are difficult to review.

This course project also needs to demonstrate concrete understanding of retrieval-augmented generation and bounded agentic workflows. The existing backend already supports authenticated repository cloning, Python-aware vector ingestion, hybrid retrieval, basic agent execution, and protected Git pushes, but these capabilities are not yet combined into one repository-scoped workflow.

The user needs a demo in which answers are grounded in one connected Repository, code generation is limited to Test Files, generated changes pass through Patch Review, and Approval can publish a non-default branch without permitting direct modification of the default branch.

The authenticated frontend currently exposes leftover template navigation and branding instead of the Repository-centered workflow. Its Repository and Repository Session behavior is difficult to discover, selecting obsolete navigation can lead to a generic error screen, session creation is implicit, and reloading an existing conversation cannot restore its complete history or durable Coding Run results.

Backend module interfaces also use nullable dependency parameters with `None` defaults in places where the dependency is required for correct production behavior. Omitting one of these dependencies can silently select a null, local, or in-memory adapter, degrade Code Generation behavior, or translate missing infrastructure into a misleading domain error. This makes the application composition less explicit and allows invalid configurations to survive until runtime.

## Solution

Build an authenticated AI Codebase Copilot workspace and FastAPI workflow for public and private Python repositories hosted on GitHub.

A user connects a Repository with a mandatory Repository Credential. The backend clones and indexes the default branch. The user creates a Repository Session permanently bound to that Repository and can then:

- Ask codebase questions answered from Repository Documents with file citations.
- Submit a Code Generation Task that may consult External References for current test-writing guidance.
- Submit a Code Generation Task through a bounded LangGraph workflow.
- Receive live progress through an Agent Stream.
- Review a generated Test Patch and Patch Review findings.
- Reject the patch or approve a commit and push to a new non-default branch.

Repository Synchronization keeps Repository Documents aligned with the latest default-branch commit through file-level incremental updates rather than a full re-index. A read-only background loop detects when the remote default branch has moved ahead of the indexed commit (Sync Availability) and shows the user a "sync now" message; the user then triggers the Synchronization Request endpoint, which runs the actual synchronization. Detection never synchronizes on its own.

The authenticated product uses an AI-chat-style workspace. Repositories and their nested Repository Sessions live in a collapsible left panel, while the main area presents Repository onboarding, processing status, credential maintenance, a contextual empty state, or the selected chat. Repository Sessions use durable URLs, restore the user's last selection, display complete paginated Session History, and reconstruct Code Generation Task results from durable Coding Runs.

The project remains a focused demonstration. It does not install dependencies, execute generated tests, create pull requests, support arbitrary coding tasks, or provide production concurrency guarantees.

Backend module interfaces prefer strict required parameters. A parameter uses `| None` only when absence is a meaningful, documented part of the domain or request contract. Required adapters, stores, factories, policies, and Code Generation invariants are supplied explicitly at the application composition root; tests explicitly select fakes, mocks, null adapters, or in-memory adapters rather than receiving them through silent defaults.

## User Stories

1. As a user, I want to connect a public GitHub Python Repository, so that I can explore its code through the copilot.
2. As a user, I want to connect a private GitHub Python Repository, so that I can use the same workflow with non-public code.
3. As a user, I want every Repository connection to require a Repository Credential, so that cloning, fetching, and an approved branch push use one consistent authentication flow.
4. As a user, I want non-GitHub repository URLs to be rejected, so that the demo has a clear provider boundary.
5. As a user, I want repositories without a usable Python codebase to be rejected or reported as unsupported, so that the system does not imply multi-language support.
6. As a user, I want Repository cloning and initial indexing to run in the background, so that the connection request does not remain blocked.
7. As a user, I want to see Repository processing status, so that I know whether cloning, indexing, readiness, or failure is current.
8. As a user, I want Repository failures to contain sanitized reasons, so that I can understand failures without exposing credentials.
9. As a user, I want the backend to record the indexed default-branch commit, so that Repository Documents have a known source snapshot.
10. As a user, I want to request Repository Synchronization manually, so that I control when the index follows upstream changes.
11. As a user, I want synchronization to fetch the latest default branch, so that new upstream commits can become available for questions and tasks.
12. As a user, I want newly added Python files to be indexed incrementally, so that synchronization does not rebuild unrelated vectors.
13. As a user, I want modified Python files to have their old Code Chunks replaced, so that stale content is not retrieved.
14. As a user, I want deleted Python files removed from Repository Documents, so that answers cannot cite code that no longer exists.
15. As a user, I want renamed Python files re-indexed under their new path, so that file citations remain correct.
16. As a user, I want the indexed commit to advance only after synchronization succeeds, so that the stored snapshot never claims a partially updated index.
17. As a user, I want synchronization status and failure information, so that I can distinguish successful, active, and failed updates.
18. As a user, I want to create a Repository Session for one Repository, so that every conversation has an explicit evidence boundary.
19. As a user, I want a Repository Session to remain bound to its original Repository, so that later messages cannot accidentally query another Repository.
20. As a user, I want to create a new Repository Session when changing repositories, so that each session remains coherent.
21. As a user, I want Session History persisted as individual exchanges, so that conversations can continue without a duplicate memory blob.
22. As a user, I want only the ten most recent Session History messages used for reformulation and planning, so that prompts remain bounded.
23. As a user, I want to ask where a behavior is implemented, so that I can locate relevant files quickly.
24. As a user, I want to ask how components interact, so that I can understand repository architecture.
25. As a user, I want follow-up questions to account for recent conversation context, so that I do not have to repeat the subject.
26. As a user, I want every codebase answer grounded only in the Repository Session's Repository Documents, so that claims do not come from another connected Repository.
27. As a user, I want file citations with codebase answers, so that I can inspect the supporting source.
28. As a user, I want the system to state when Repository Documents are insufficient, so that uncertainty is visible instead of hidden by model guesses.
29. As a user, I want ordinary repository questions to avoid web search, so that external information does not contaminate repository claims.
30. As a user, I want Code Generation Tasks to consult current documentation or testing best practices when useful, so that generated tests can follow current framework guidance.
31. As a user, I want Repository Documents and External References shown separately for Code Generation Tasks, so that I can distinguish codebase facts from test-writing guidance.
32. As a user, I want question progress and answer tokens streamed through an Agent Stream, so that the interface provides immediate feedback.
33. As a user, I want to submit a free-text Code Generation Task, so that I can describe the code behavior that needs tests.
34. As a user, I want Code Generation Tasks limited to adding or improving tests, so that the demo does not silently become a general code-editing agent.
35. As a user, I want the planner to produce Retrieval Requests, so that retrieval targets definitions, callers, related tests, configuration, and conventions.
36. As a user, I want planner-suggested paths treated as untrusted hints, so that the LLM cannot read arbitrary filesystem locations.
37. As a user, I want code generation to use only validated Repository Documents, so that generated tests reflect the connected codebase.
38. As a user, I want the generator to return complete Test File contents, so that the backend does not depend on an LLM producing a perfectly applicable unified diff.
39. As a user, I want the backend to derive the unified diff with Git, so that the displayed patch accurately reflects written changes.
40. As a user, I want existing Test Files to be eligible for modification, so that the agent can improve current coverage.
41. As a user, I want new Python Test Files allowed only under an existing test root, so that the agent follows the Repository's established structure.
42. As a user, I want paths outside the checkout rejected, so that a generated patch cannot escape the Repository.
43. As a user, I want symlink targets rejected, so that path validation cannot be bypassed.
44. As a user, I want non-Python files rejected from a Test Patch, so that the demo remains within its Python scope.
45. As a user, I want application and source files rejected from a Test Patch, so that code generation cannot alter production behavior.
46. As a user, I want invented test roots rejected, so that the agent does not impose a new project structure.
47. As a user, I want Patch Review to verify task alignment, so that the patch addresses the requested testing goal.
48. As a user, I want Patch Review to check Repository conventions and visible imports, so that generated tests resemble existing tests.
49. As a user, I want Patch Review to detect unrelated changes, so that the proposal remains narrowly scoped.
50. As a user, I want Patch Review to verify that only Test Files changed, so that the test-only boundary is enforced twice.
51. As a user, I want configurable Generation Retries after Patch Review scores a patch below threshold, so that the workflow can improve weak patches without looping indefinitely.
52. As a user, I want exhausted Generation Retries to escalate the best-scoring Test Patch to human review, so that a low score is not misrepresented as a Run Failure.
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
75. As an authenticated user, I want to land in the AI Codebase Copilot workspace instead of a generic Dashboard, so that the application immediately reflects its purpose.
76. As a user, I want FastAPI template branding, social links, and the generic footer removed, so that the interface belongs to the AI Codebase Copilot product.
77. As a user with no Repositories, I want a central “Add your code repository” empty state, so that my first action is obvious.
78. As a user, I want Repository registration on a dedicated authenticated screen with Back and Cancel actions, so that onboarding is focused without losing workspace context.
79. As a user with existing Repositories, I want an add action beside the Repositories heading, so that I can connect another Repository without returning to an empty state.
80. As a user, I want Repository registration to accept a GitHub URL, mandatory Repository Credential, and optional numeric expiration period in days, so that the form matches the backend contract without asking me to calculate a date.
81. As a user, I want successful Repository registration to return me to the workspace with the new Repository selected, so that I can immediately see what happens next.
82. As a user, I want pending, cloning, and indexing Repository status to update live, so that I know when Repository Sessions become available.
83. As a user, I want failed Repository processing to show its sanitized reason without offering an unsupported retry action, so that the interface is honest about available recovery behavior.
84. As a user, I want to update a Repository Credential without changing its processing status, so that credential maintenance has no hidden side effects.
85. As a user, I want Repositories displayed as collapsible groups in the left panel, so that the workspace resembles a familiar AI chat interface.
86. As a user, I want only the active Repository expanded, so that the Repository Session list remains scannable.
87. As a user, I want existing Repository Sessions nested beneath their Repository, so that each conversation's evidence boundary is visible.
88. As a user, I want Repository Session creation to require an explicit “New session” action, so that selecting a Repository never creates unwanted data.
89. As a user, I want each Repository Session to have a durable URL containing its Repository and session identities, so that refresh and direct navigation restore the correct conversation.
90. As a user, I want browser refresh and back/forward navigation to preserve Repository Session selection, so that standard browser behavior remains reliable.
91. As a returning user, I want the workspace to reopen my most recently used accessible Repository Session, so that I can continue where I stopped.
92. As a user switching Repositories, I want that Repository's last-used session restored when available, so that each Repository retains its own working context.
93. As a user viewing a ready Repository without a selected session, I want a central “Start a new session” state, so that the next action is clear without automatic creation.
94. As a user, I want Repository Session creation disabled until its Repository is ready, so that I cannot enter a conversation without Repository Documents.
95. As a user, I want a newly created Repository Session titled “New session,” so that blank conversations have a recognizable placeholder.
96. As a user, I want the first request to create a short deterministic Repository Session title, so that I can recognize the conversation without a naming dialog or another model call.
97. As a user, I want Repository Sessions ordered by newest activity, so that my current work stays near the top.
98. As a user, I want the complete persisted Session History displayed when reopening a Repository Session, so that older conversation context is not hidden by the AI prompt limit.
99. As a user, I want the newest 50 Session History messages loaded initially, so that long conversations open promptly near my latest work.
100. As a user, I want older Session History loaded when I scroll upward without losing my scroll position, so that I can review a long conversation naturally.
101. As a user, I want full UI history kept separate from the ten-message AI context window, so that viewing older messages does not silently enlarge prompts.
102. As a user, I want Code Generation Tasks recorded in their Repository Session chronology, so that coding work survives reload alongside ordinary questions.
103. As a user, I want reloaded coding cards reconstructed from the current durable Coding Run, so that review, failure, Approval, rejection, patch, and branch information is never stale.
104. As a user, I want Appearance and profile controls to remain at the bottom of the responsive left panel, so that familiar account controls remain consistently available.
105. As a mobile user, I want Repository and Repository Session navigation to work through the existing sidebar drawer, so that the workspace remains usable on a small screen.
106. As a Repository owner, I want Approval to open a Pull Request from the approved branch into my default branch, so that I can review and merge generated tests with GitHub's normal review flow instead of opening the PR by hand.
107. As a Repository owner, I want the Pull Request opened only after the branch is successfully pushed, so that the PR always references a branch that exists on the remote.
108. As a Repository owner, I want the Pull Request body to contain the Patch Review score, the pass threshold, and the categorized findings, so that I can judge the proposed Test Files and the assessment together on GitHub.
109. As a Repository owner, I want the Pull Request to target my Repository's default branch as its base, so that the proposal lands where I merge my work.
110. As a Repository owner, I want Approval to never push to or merge my default branch, so that proposing tests can never overwrite protected history.
111. As a Repository owner, I want merging the Pull Request to remain my decision on GitHub, so that nothing is merged on my behalf.
112. As a Repository owner, I want the response to Approval to tell me the Pull Request's URL, so that I can jump straight to reviewing it.
113. As a Repository owner, I want pull-request creation to use the same Repository Credential as clone, fetch, and push, so that I do not configure a second secret.
114. As a Repository owner, I want a clear failure when my credential lacks pull-request write permission, so that I can fix the token scope rather than guess.
115. As a Repository owner, I want a pull-request creation failure reported as its own failure stage distinct from a push failure, so that I understand the branch was pushed and only the Pull Request is missing.
116. As a Repository owner, I want the Repository Credential never exposed in pull-request creation errors or logs, so that approving tests cannot leak my token.
117. As a Repository owner connected to GitHub Enterprise, I want pull-request creation to honor a configurable API base URL, so that the feature works against my GitHub host.
118. As a Repository owner, I want no Pull Request, issue, or comment created on the question or rejection paths, so that only an explicit Approval writes to GitHub.
119. As a backend maintainer, I want required dependencies represented by non-nullable parameters, so that invalid application composition is rejected before a workflow runs.
120. As a backend maintainer, I want the application composition root to select production adapters explicitly, so that persistence, publishing, checkout behavior, and checkpoint durability cannot change through parameter omission.
121. As a backend maintainer, I want null and in-memory adapters selected explicitly in tests, so that test isolation remains intentional and visible.
122. As a backend maintainer, I want module interfaces to depend on protocols or callable interfaces instead of unnecessary concrete implementations, so that strict dependency requirements do not remove useful substitution seams.
123. As a backend maintainer, I want missing infrastructure distinguished from missing domain records, so that configuration errors cannot appear as ordinary not-found outcomes.
124. As a backend maintainer, I want review policy values resolved once during application composition, so that Patch Review and Generation Retries use one visible configuration.
125. As a backend maintainer, I want required Code Generation checkout context validated before retrieval and generation, so that missing context cannot silently discard candidate paths or weaken validation.
126. As a test author, I want fakes and mocks checked against the same interfaces used by production modules, so that tests remain representative without requiring production infrastructure.
127. As a backend maintainer, I want nullable parameters retained when absence carries real domain meaning, so that strict typing does not replace clear optional behavior with artificial sentinel values.
128. As a backend maintainer, I want every remaining `None` default to have an identifiable absence case, so that future contributors can distinguish optional domain data from omitted dependencies.

## Implementation Decisions

- The backend supports public and private Python repositories hosted on GitHub only.
- A Repository Credential is mandatory for every Repository and is used through non-interactive Git authentication for clone, fetch, and push.
- Existing credential encryption and sanitized Git error handling remain the authentication boundary.
- Repository registration schedules clone and initial indexing as a FastAPI background task.
- Repository Synchronization is manually triggered and also runs as a FastAPI background task.
- Per ADR 0008, a read-only background loop polls the remote default-branch head with `git ls-remote` to detect **Sync Availability** — that the remote has advanced beyond the indexed commit. Detection only surfaces a "sync now" message to the user through the Repository read model; it never opens the checkout, never advances the indexed commit, and never runs Repository Synchronization. Bringing the index up to date remains a user action: the user triggers the existing Synchronization Request endpoint, which performs the actual sync against the latest remote.
- The Repository model records the commit SHA represented by Repository Documents.
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
- The complete Session History is available to the UI through an ownership-scoped paginated read model, while at most the ten most recent messages are supplied to reformulation and planning.
- Repository questions use Repository Documents exclusively for claims about code and behavior.
- Insufficient Repository Documents produce an explicit limitation response rather than an unsupported answer.
- Web search is unavailable to ordinary Repository questions and may be invoked only on the Code Generation Task path for current test-writing guidance.
- Responses separate Repository sources from External References.
- Questions and Code Generation Tasks use synchronous server-sent events.
- Agent Stream events cover stage progress, generated content, citations or reviewer findings, and the final persisted result.
- Agent workflows do not use polling, WebSockets, or background execution.
- Client disconnect during a Coding Run cancels processing, records failure, and triggers checkout cleanup.
- Code Generation Tasks may change Test Files only.
- The LangGraph workflow follows a bounded score-and-escalation progression:

  ```text
  plan
    -> retrieve
    -> generate
    -> review
    -> revise while below threshold and Generation Retries remain
    -> review
    -> awaiting approval when accepted or when Generation Retries are exhausted
  ```

- Planner output contains Retrieval Requests and optional candidate paths, not unrestricted file-read instructions.
- Candidate paths are normalized, confined to the Repository checkout, and verified before use.
- Retrieval determines the actual Repository Documents supplied to the code generator and Code Reviewer.
- The generator returns structured complete-file proposals rather than unified diff text.
- The backend validates and writes proposed Test Files, then obtains the canonical unified diff from Git.
- Existing recognized Python Test Files may be modified.
- New Python Test Files may be created only within an existing `tests` or `test` root.
- Path escape, symlink, non-Python, source-file, and invented-test-root proposals are rejected before writing.
- Patch Review assesses task satisfaction, consistency with retrieved code and existing tests, visible import validity, unrelated modifications, and the Test File boundary.
- Patch Review does not execute tests, install dependencies, or claim runtime correctness.
- Patch Review returns a score and categorized findings; the backend applies the configurable acceptance threshold and independently hard-fails Test File boundary escapes.
- Generation Retries default to two opportunities. Exhaustion escalates the best-scoring Test Patch to the owner rather than failing the Coding Run.
- The same generator agent performs initial generation and revision and may consult External References on either path.
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
- Approval and rejection decisions resume the paused Coding Run through the same Repository Session Agent Stream entry point.
- The authenticated frontend uses the AI Codebase Copilot brand and removes generic Dashboard, Items, FastAPI social links, and the template footer.
- The collapsible left panel retains Appearance and user profile controls at its bottom and uses its main area for Repository groups and nested Repository Sessions.
- A zero-Repository workspace displays a central onboarding action; Repository registration uses a dedicated authenticated route that keeps the left panel visible.
- Repository registration accepts a GitHub repository URL, mandatory Repository Credential, and optional positive token-expiration period expressed as a number of days.
- Successful registration selects the new Repository and returns to a status view. Active processing statuses are polled until ready or failed.
- Updating a Repository Credential is available from the Repository details view and never changes or restarts Repository processing status.
- Repository groups are collapsible, with only the active Repository expanded. Repository Session creation is explicit and available only for ready Repositories.
- Repository Sessions use durable routes containing both Repository and Repository Session identities. Device-local last-used selections provide root-workspace and per-Repository restoration, with safe fallback for stale or inaccessible values.
- A new Repository Session begins as “New session.” Its first normalized user request deterministically supplies a stable title of at most 60 display characters without an LLM call.
- User requests and resolved Coding Run decisions update Repository Session activity. Lists are ordered by descending activity with deterministic tie-breaking.
- Full Session History pagination initially returns the latest 50 messages in chronological display order and supports loading older pages upward without changing the AI context window.
- Per ADR 0005, Session History owns chronology and references durable Coding Runs for Code Generation Tasks; mutable patch, findings, and lifecycle snapshots are not duplicated into Session History.
- Reloaded coding cards reconstruct their current state from the durable Coding Run record while Repository-question citations remain structurally attached to assistant messages under ADR 0001.
- Per ADR 0006, Approval opens a Pull Request from the pushed generated branch into the Repository's default branch, after a successful push, carrying the Patch Review score, threshold, and findings in the PR body.
- GitHub API access uses the PyGithub library, constructed with the Repository Credential and a configurable API base URL (default `https://api.github.com`, overridable for GitHub Enterprise). The `gh` CLI and hand-rolled HTTP clients are not used.
- Pull-request creation extends the existing `PatchPublisher` port (which the approve node already uses for commit and push) with an `open_pull_request` operation; the production adapter owns the credential and the network, and the existing fake keeps graph and node tests offline.
- PyGithub failures translate to a new sanitized `GitHubError` mirroring `GitError`, with the Repository Credential redacted. Pull-request creation failure is a Run Failure on a distinct `github_pull_request` stage, separate from `git_push`.
- The Approval response surfaces the created Pull Request's URL to the owner; default-branch protection in the push path is unchanged.
- Backend interfaces use non-nullable parameters for required adapters, stores, factories, policies, and execution invariants. `| None = None` is not used merely to make construction or testing convenient.
- `| None` remains valid when absence is part of the documented domain or request contract, including optional collection filters, nullable persisted lifecycle fields, optional user input, optional credentials for unauthenticated operations, and optional error-detail overrides.
- Strict dependency parameters continue to target protocols or callable interfaces where multiple adapters exist. Strictness does not require callers to depend on a concrete production implementation.
- The unified graph requires callers to provide its Coding Run recorder, workspace factory, Patch Publisher factory, and checkpointer explicitly. Production composition supplies durable adapters; isolated tests explicitly supply null, fake, or in-memory adapters.
- The Repository Session application module requires its Coding Run store. Absence of that store is a composition error and must not be translated into a `Coding Run` not-found result.
- Patch Review threshold and Generation Retries configuration are resolved at application composition and passed as required policy values to the graph modules that apply them. A configured zero remains a valid explicit value where the policy permits it.
- Code Generation requires checkout context before Repository Document partitioning, Test File validation, or workspace mutation. Missing checkout context produces an explicit precondition failure rather than silently omitting candidate paths.
- Default construction that is entirely internal to a module may remain when it does not weaken the module's external invariants or silently replace a required external adapter. Each such default is assessed individually rather than removed mechanically.
- Existing FastAPI response contracts, Agent Stream vocabulary, Coding Run state transitions, persistence schema, and GitHub behavior do not change as part of this strict-interface work.

## Testing Decisions

- Tests assert externally visible behavior, persisted state, emitted Agent Stream events, Git effects, and vector-store interactions. They do not assert prompt wording, private helper calls, or LangGraph's internal implementation details.
- Playwright browser tests exercise the authenticated shell, zero-Repository onboarding, dedicated registration, live Repository status, credential updates, nested Repository Session navigation, durable URLs, restoration after reload, mobile drawer behavior, and upward history pagination. API responses remain mocked in browser tests, following the existing frontend suite.
- Browser tests assert visible behavior and navigation outcomes rather than component structure, internal state, or styling implementation details.
- FastAPI route tests use `TestClient` and dependency overrides, following the existing repository route tests. They cover authentication and ownership, Repository Session binding, background synchronization scheduling, SSE content types and terminal events, run lookup, Approval, rejection, and sanitized errors.
- FastAPI route tests additionally cover ownership-safe full-history pagination, stable page boundaries, coding-entry serialization, and reconstruction from the current Coding Run.
- SSE tests consume complete test streams and assert ordered stage events plus the final result. Token chunk boundaries are not treated as stable behavior.
- Repository service tests use fake stores, fake Git commands, and fake ingestion resources, following existing service tests. They cover GitHub-only validation, initial processing, incremental synchronization status, commit advancement, and failure preservation.
- Incremental synchronization tests cover add, modify, delete, rename, no-change, fetch failure, diff failure, vector-write failure, and the rule that indexed commit SHA advances only on full success.
- Ingestor tests use fake Weaviate resources, following existing RAG ingestion tests. They cover Code Chunk metadata, file-level replacement, deletion by source or parent identity, and user-tenant isolation.
- Retriever tests use fake vector-store resources, following existing retrieval tests. They verify that Repository identity filters are always applied and that Repository Documents from another Repository cannot enter the result.
- RAG pipeline tests use fake model, retriever, and chain dependencies, following existing pipeline construction tests. They cover repository-scoped construction, the ten-message recent Session History boundary, insufficient-evidence responses, file citations, and the rule that ordinary Repository questions cannot reach web search.
- LangGraph tests use deterministic fake planner, retriever, generator, reviewer, and event sinks. They cover the accepted path, revision within budget, below-threshold budget exhaustion escalating to human review, generation failure, validation failure, disconnect cancellation, and event ordering.
- LangGraph tests treat node outputs and state transitions as contracts. They do not call external LLM or Tavily services.
- Patch validation tests operate on temporary Repository checkouts and cover existing Test Files, new files in existing test roots, path traversal, absolute paths, symlinks, non-Python files, source files, and invented test roots.
- Git command tests mock subprocess execution, following existing Git tests. They cover checkout restoration, temporary branch creation, diff generation, commit, push, default-branch rejection, token redaction, and local branch cleanup.
- Pull-request creation tests substitute a fake PyGithub client (no network), following the fake-store and fake-Git-commands pattern. They cover opening the PR with the default branch as base, the Patch Review rendered in the PR body, the returned PR URL, the push-then-PR ordering, credential redaction in errors, a permission-denied failure mapped to the `github_pull_request` stage, and that no Pull Request is created on the question or rejection paths.
- Coding Run service tests cover every permitted and rejected state transition.
- Failure tests verify structured failure stages and sanitized user-visible reasons without requiring exact provider error text.
- Persistence tests follow existing store tests and cover Repository indexed commit state, Repository Session ownership and binding, Session History ordering, Coding Run state, Test Patch persistence, Patch Review findings, and Run Failure fields.
- Persistence and service tests additionally cover deterministic first-request titles, stable title preservation, activity ordering, complete-history pagination independent from the ten-message AI window, and durable Session History references to Coding Runs.
- Model and migration tests verify required foreign keys, cascade behavior, uniqueness constraints, enum values, and removal of duplicate session memory.
- Existing Agent Stream tests remain the regression seam for ensuring Repository questions, Code Generation Tasks, and Approval or rejection decisions update durable conversation state without changing terminal-event behavior.
- Application composition tests are the highest seam for strict dependencies: they verify that production providers supply the durable recorder, workspace factory, Patch Publisher factory, checkpointer, Coding Run store, and resolved review policy.
- Interface-focused tests verify that required dependencies cannot be omitted and that explicit null, fake, mock, and in-memory adapters remain accepted when they satisfy the same protocol or callable interface.
- Unified graph tests explicitly provide every runtime adapter. They verify external graph behavior and emitted Agent Stream events rather than asserting private calls used to select adapters.
- Repository Session application tests explicitly provide a fake Coding Run store, including tests unrelated to Coding Run lookup, so construction matches the production interface.
- Code Generation tests cover missing checkout context as an explicit precondition failure and verify that valid context continues to confine candidate paths and Test Files.
- Review policy tests pass explicit threshold and Generation Retries values, including zero and configured defaults resolved by the composition root, so falsey values cannot be mistaken for omitted configuration.
- A static type-checking regression check covers the strict interfaces and their production and test adapters, ensuring protocol conformance without coupling tests to concrete production implementations.
- Tests do not clone real repositories, push real branches, install target Repository dependencies, execute generated tests, call OpenAI, call Tavily, or require a live Weaviate instance.
- A small manually operated end-to-end demo remains appropriate for course presentation: connect a controlled GitHub Repository, ask a cited question, generate a Test Patch, reject one run, approve another, and verify the non-default remote branch.

## Out of Scope

- GitLab, Bitbucket, self-hosted Git providers, and local-only repositories.
- Languages other than Python.
- General feature implementation, bug fixing, refactoring, or application-code modification.
- Test execution, dependency installation, virtual-environment creation, coverage analysis, linting, and type checking inside connected repositories.
- Runtime verification of generated tests.
- Merging the Pull Request, auto-merge, draft pull requests, requesting reviewers or assignees, and remote generated-branch deletion. (Opening the Pull Request on Approval is in scope per ADR 0006.)
- Creating GitHub issues or pull-request comments, and any GitHub writes on the question or rejection paths.
- GitHub Actions creation, management, or check-status integration.
- Automatic synchronization — running a Checkout Operation that mutates the checkout and index — through schedules, webhooks, or push events. Polling is used only to detect Sync Availability and show the user a "sync now" message; it never synchronizes on the user's behalf. The user always triggers the Synchronization Request endpoint to perform the actual sync.
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
- Automatic Repository Session creation when a Repository is selected.
- Manual Repository Session rename and delete controls.
- Repository-processing retry behavior or a retry-processing API.
- Changing Repository processing status as a side effect of updating its Repository Credential.
- A date picker for Repository Credential expiration; the contract remains an optional numeric period in days.
- Duplicating mutable Coding Run patches, findings, or lifecycle snapshots inside Session History.
- Production security, scalability, observability, cost controls, and multi-region deployment beyond what is necessary for the course demo.
- Removing every nullable type mechanically. Nullable fields and parameters remain in scope wherever absence is a real domain, persistence, configuration, or request state.
- Replacing protocols with concrete production classes merely to make parameters non-nullable.
- Changing user-visible behavior, Agent Stream events, persistence schema, or Coding Run lifecycle semantics while tightening module interfaces.

## Further Notes

- The purpose is to demonstrate RAG, hybrid retrieval, repository-scoped evidence, LangGraph state and routing, bounded agent revision, streaming feedback, human Approval, and Git integration.
- Existing repository, Git, RAG, Weaviate, FastAPI, authentication, and persistence patterns should be extended rather than replaced.
- The shared checkout design is intentionally simple because concurrent requests are outside scope. Cleanup behavior is still required so sequential demo runs remain deterministic.
- Patch Review communicates evidence-based confidence but must not imply that generated tests pass, because execution is explicitly excluded.
- Complete Session History is a presentation concern distinct from AI context: the UI may page through every persisted entry while reformulation and planning receive only the latest ten messages.
- ADR 0005 records the decision to reference durable Coding Runs from Session History and reconstruct current coding cards rather than persisting duplicate snapshots.
- Approval pushes the generated branch and opens a Pull Request into the default branch, carrying the Patch Review in its body (ADR 0006). The Pull Request is the terminal integration artifact; reviewing and merging it remain the owner's decision on GitHub.
- The implementation plan and domain glossary remain the controlling references for terminology and scope.
- The preferred backend style is strict-by-default: require a value unless the interface can name and test the meaning of its absence. Convenience for tests is handled with explicit adapters, fakes, or mocks rather than nullable production dependencies.
