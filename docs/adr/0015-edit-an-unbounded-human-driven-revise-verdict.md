# Edit: an unbounded human-driven revise verdict on an escalated Test Patch

## Status

accepted

Extends the owner's human-in-the-loop decision on the intent-routed graph (ADR [0002](0002-intent-routed-unified-langgraph.md)) from a binary approve/reject into a three-way **Owner Decision**. Consumes the **Owner Decision** and **Edit** glossary terms. Reuses the `revise()` path and the **Generation Retries** arithmetic rather than adding a parallel loop.

## Context and decision

When a generated Test Patch escalates, the owner could only **approve** or **reject** it: `HumanDecisionRequest.approved` was a boolean, and `_route_after_decision` chose `approve_patch` vs `discard_patch` off it. A latent `feedback` field was already plumbed from the resume payload into `human_feedback` graph state — but nothing consumed it. Owners who found a patch *nearly* right had no move except reject-and-start-over, throwing away a good plan and a mostly-good patch.

We added a third verdict, **Edit**: the owner submits free-text feedback and the same Coding Run returns to generation, **revises the already-generated Test Files in place** against that feedback, then re-reviews and re-escalates for a fresh decision. The owner never hand-edits files — the model authors every revision. The verdict field became an enum `{approve, reject, edit}`, with feedback required for `edit`.

Key mechanics, chosen deliberately:

- **Revise in place, not from scratch.** The owner's feedback is written *about the patch on screen*, so the model must act on the existing files and diff. Edit routes back to `generate_code`'s existing `revise()` path (`prior_files` + `diff` + `findings`), threading the accumulated `human_feedback` in as an authoritative requirement alongside the current review findings. A new `apply_edit` node — mirroring the approve/reject symmetry (each verdict → its own node) — appends the feedback, resets `generation_retries` to 0, and keeps the review/patch/branch state intact so `generate_code` needs no new mode.
- **Reset the automatic budget, reuse its arithmetic.** "Reset to 0" means the automatic Generation Retries counter, not the files. The Edit's own feedback-driven revise counts as the first spend of that fresh budget, so each round is one owner-steered revise plus one automatic below-threshold cleanup before re-escalating.
- **Unbounded, because a human gates every round.** Generation Retries is capped precisely because it is automatic; Edit re-escalates and re-pauses each time, so there is no runaway to cap. Feedback **accumulates** across rounds on top of the original Code Generation Task.
- **Widen the resumability gate.** `awaiting_decision` previously admitted only `awaiting_approval`. A below-threshold escalation persists as `changes_requested`, so an Edit that re-escalates below threshold would strand the owner at a paused graph the backend refused to resume. `awaiting_decision` now admits `changes_requested` too; `_assert_checkpoint_awaits_decision` still independently confirms the LangGraph thread is genuinely paused at `await_decision`. This incidentally makes any below-threshold escalation actionable, closing a pre-existing dead-end.

Edit carries **no dedicated run status** and adds **no Agent Stream event**: the resumed run cycles through the ordinary `generating`/`reviewing` states and re-surfaces the existing `ReviewResult` escalation event, keeping the closed stream vocabulary of ADR [0002](0002-intent-routed-unified-langgraph.md) untouched.

## Considered options

- **From-scratch regeneration (rejected).** The owner's original ask was "reset everything to 0," which first read as discarding the patch and regenerating blank. Rejected once it was clear the feedback is written against *what was generated* — a blank regeneration would ignore the very files the feedback references.
- **A brand-new Coding Run per Edit (rejected).** Violates the one-active-run-per-Repository invariant and discards the still-valid plan and retrieved Repository Documents for no gain; the owner is steering the tests, not re-asking the task.
- **Bounded Edits (rejected).** No safety payoff when a human gates each round; only frustrates the owner.
- **Replace-not-accumulate feedback (rejected).** The owner refines against successive attempts, so each round's note builds on the last rather than superseding it.
- **A dedicated `changes_requested`-style status for a pending Edit (rejected).** `apply_edit` hands straight to `generate_code`, which records `generating`; the run needs no lingering intermediate state, and `changes_requested` already means below-threshold escalation.

## Consequences

- `changes_requested` is now a **resumable** state, not a terminal one; the test that enshrined it as non-resumable is inverted.
- `human_feedback` is now load-bearing: it steers `revise()` and persists in checkpointer graph state. It is **not** surfaced in the transcript — showing the owner's words on reload is deferred to the coding-card reload work rather than built here.
- The generator's `revise()` gains a `feedback` argument and its prompt must frame owner feedback as authoritative over reviewer findings.
