# Scored Patch Review with configurable Generation Retries that escalate to human review

## Status

accepted

Revises issues [11](../issues/11-review-test-patch.md), [12](../issues/12-perform-bounded-revision.md), [14](../issues/14-reject-reviewed-test-patch.md), and [23](../issues/23-name-the-revision-attempt-budget.md), which encode the boolean-verdict, single-attempt, fail-on-exhaustion review loop this ADR replaces.

## Context and decision

The code-generation loop shipped (issues 11–14, 23) with three coupled rules: the Code Reviewer returned a boolean `accepted`; the code generator got exactly one retry; and a second rejection ended the Coding Run as a `reviewing`-stage `RunFailure`. In practice the last rule is poor product behaviour — a user who asked for tests is shown a *failed run* with no actionable next step, even though a real (if imperfect) Test Patch exists. We also carried a separate, deliberately tool-free revision agent with its own revision prompt, and the post-review routing lived in a conditional-edge function rather than as a visible graph node.

We decided to restructure the loop around a **score** and **escalation**:

- **The Code Reviewer scores, the backend decides.** `PatchReview` drops `accepted` and returns `score: int` (0–10) plus categorized findings. Pass/fail is backend policy: `accepted = score >= REVIEW_PASS_THRESHOLD` (default 7). The independent Test File check remains a hard override — an escaped path fails the patch regardless of score, so the Code Reviewer is never the sole gate.
- **Generation Retries are configurable.** The fixed single retry becomes `MAX_GENERATION_RETRIES` (default 2).
- **Exhaustion escalates, it does not fail.** A new explicit review gate reads the score and spent Generation Retries: at/above threshold → await decision; below threshold with retries left → revise; below threshold with retries exhausted → also await decision, carrying the best attempt with its score and findings. The owner always inspects and decides. `RunFailure` is reserved for true stage errors (generation crash, Git failure, Code Reviewer crash).
- **One generator agent.** The separate tool-free `_revision_agent` is removed; the single `web_search`-capable agent performs both generation and revision, with revision context (prior diff, findings) carried in the human message. Revision may now web-search.
- **`RunApproved` gains a user-facing `message`** so an approved push tells the owner a branch was created and where to look.

## Considered options

- **Score replacing the boolean vs. score alongside it** — chose replacement. Keeping a model-supplied `accepted` *and* a score splits the verdict between model and policy and makes the threshold cosmetic. Letting the backend own the threshold keeps the pass bar a tunable, auditable decision and the boundary check an explicit hard override.
- **Exhaustion: escalate vs. soft terminal vs. softened failure** — chose escalate-to-human. A distinct non-error terminal (`ReviewInconclusive`) still dead-ends the user with no approval path; softening the `RunFailure` copy keeps the framing we set out to remove. Escalating means a low score is never a failure and the owner always gets a decision. Cost: `await_decision` must surface the score/findings so an owner can judge a below-threshold patch, and the human reject path (issue 14, `RunRejected`) stays as the deliberate "no" — only auto-failure on a low score is gone.
- **Configurable Generation Retries vs. one fixed retry** — chose configurable, default 2 (one more opportunity than the shipped behaviour). The retry policy owns the configurable limit and escalation rule.
- **One agent vs. keeping tool-free revision** — chose one `web_search`-capable agent. The deliberate tool-free constraint (ADR-era rationale in `generator.py`) assumed revision should not reopen web research; in practice many findings ("uses a deprecated pytest API") are exactly what web search fixes. Cost: revision is no longer guaranteed offline/deterministic, and `REVISION_SYSTEM_PROMPT` retires into the assembled human message.
- **Stream vocabulary** — kept the closed, typed `AgentStreamEvent` union (issues 19/22/28) rather than collapsing to one generic envelope; `ReviewResult` absorbs `score`/`threshold`, `RunApproved` absorbs `message`, and the never-emitted `PatchResult` leaves the wire union (it stays an internal state type). A generic `{kind, payload}` envelope was rejected for trading away the typed, exhaustively-matchable client contract those issues defend.
