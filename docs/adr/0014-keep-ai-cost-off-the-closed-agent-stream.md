# Keep AI cost off the closed Agent Stream; expose it through read endpoints

## Status

accepted

Reaffirms the closed Agent Stream vocabulary of ADR [0002](0002-intent-routed-unified-langgraph.md) and its sealed wire seam (ADR [0028](../issues/28-close-agent-stream-wire-seam.md)). Consumes the **AI Cost** glossary term and the per-call estimate of ADR [0013](0013-estimate-ai-cost-from-token-usage-and-a-local-price-table.md). No new Agent Stream event type is added.

## Context and decision

AI Cost wants to be visible to the owner: the cost of the turn they just ran, the running total of a session, and the per-Repository and per-user rollups. The tempting place to put a live number is the Agent Stream — everything else the user sees during a turn already flows there. But that stream is a **closed, typed event vocabulary** (`AgentStreamEvent`), deliberately sealed so a Repository question or Code Generation Task can report only a fixed set of outcomes, and an entire ADR (0028) exists to keep that wire seam from leaking. Cost is not a step in answering a question or generating a patch — it is an after-the-fact bookkeeping fact about the turn.

We decided to **keep cost entirely off the Agent Stream** and expose it through ordinary owner-scoped read endpoints over the persisted `usage_record` rows.

- **Capture, don't stream.** A per-turn LangChain callback handler (injected via the existing `config["callbacks"]` at the three `graph.stream` sites) accumulates per-call usage; the rows are persisted at end of turn — in a `finally` path so a failed or disconnected turn still records the spend it incurred. The SSE frames the user sees are untouched.
- **Read, keyed by the ids the stream already hands out.** The terminal events already carry the anchors a client needs: `Result.assistant_message_id` for a question, `coding_run_id` for a Code Generation Task. So "show this turn's cost the moment it finishes" and "show each card's cost on reload" are the *same* GET against those ids — no streamed number, no client-side accumulation that could drift from the persisted truth.
- **Owner-scoped, summed on read.** Per-turn, per-session, per-Repository, and per-user figures are all sums of the same `usage_record` rows, gated by the existing ownership checks; any global rollup is superuser-only. Every entity (Repository, Session, Run) has exactly one owner, so this needs no new sharing model.

## Considered options

- **Read endpoints vs. a new `Cost` stream event vs. cost fields on existing terminal events** — chose read endpoints. A new event type reopens the closed vocabulary that ADR 0028 sealed, and forces the SSE adapter and the frontend reader to grow for a number the user does not act on mid-turn. Bolting `cost`/`tokens` fields onto the six terminal events (`Result`, `ReviewResult`, `RunApproved`, `RunRejected`, `RunNoChanges`, `RunFailure`) mutates documented shapes and scatters the same concept across every outcome. A read endpoint adds zero stream surface and leans on persistence we are building anyway. This mirrors ADR 0010's "log-only, not a stream event" call for a similarly non-actionable signal.
- **Stream the live number vs. fetch after the turn** — chose fetch. A token-by-token cost ticker is the only thing the read path cannot do, and it is not worth reopening the wire seam; the figure appearing the instant the turn completes is indistinguishable for the owner's purposes and is the same number that survives reload.

## Consequences

- **No true real-time ticker.** Cost appears on turn completion and on reload, not rising token by token. Accepted: it is a bookkeeping figure, not part of the answer.
- **The frontend makes an extra read per turn/card.** A small GET keyed by an id the client already holds, cacheable, and cheap relative to the turn it reports on.
- **The Agent Stream and its ADRs (0002, 0028) stay closed.** Adding cost required no change to the typed union, the SSE adapter, or the stream contract — the deliberate point of this decision.
