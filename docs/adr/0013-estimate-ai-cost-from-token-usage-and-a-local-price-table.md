pla# Estimate AI cost from token usage and a local price table

## Status

accepted

Introduces the **AI Cost** glossary term in `CONTEXT.md`. Builds on the cross-provider fallback of ADR [0010](0010-cross-provider-llm-retry-and-fallback.md): because a transient failure can move a call from its primary to its fallback model, cost is keyed off the model the *response* reports, not the configured primary. Captured per LLM call across the unified graph (ADR [0002](0002-intent-routed-unified-langgraph.md)) and recorded durably alongside the other per-session relational state.

## Context and decision

We want the money figure for the AI work each turn consumes, attributed to the user, Repository, Repository Session, and the individual turn. The obvious first instinct — "read the cost off the API response" — does not work here: this app calls OpenAI and Anthropic **directly** through `langchain-openai` / `langchain-anthropic`, and those responses carry token *usage* only, never a dollar amount. A monetary figure exists only on a provider's invoice, or inside a billing **gateway** (OpenRouter, a LiteLLM proxy) that sits in front of the providers and injects a `cost` field. We have no such gateway, and adding one is a request-path rearchitecture that also cuts across ADR 0010's fallback wiring.

So cost is necessarily **derived**, not reported: `cost = input_tokens × input_rate + output_tokens × output_rate`. We decided to compute it from the provider-reported token counts and a **small local per-model price table**, behind a single `price_for(model, input_tokens, output_tokens)` function.

- **Tokens are real; the rate is local.** Token counts come straight from the provider response (`usage_metadata`), so usage is exact. Only the per-1M-token rate is maintained by us — four model ids today (`gpt-4o`, `gpt-4o-mini`, `claude-haiku-4-5`, `claude-sonnet-4-6`).
- **Key the rate off the model the response reports.** ADR 0010 means a call issued to a primary may be served by its cross-provider fallback. Reading the model from the response (not from settings) makes a fallback-served call priced as the model that actually ran.
- **Fail loud on an unknown model.** An id missing from the table records the usage with `cost = null` and emits a WARNING, rather than silently substituting another model's rate. Under-reporting a Claude call at gpt-4o-mini rates would be a ~20× error hidden behind a plausible-looking number; a null with a warning is a visible, correctable gap.
- **One function isolates the source.** Every cost computation goes through `price_for`, so swapping the local table for a maintained library (`tokencost`, LiteLLM's map) later is a one-module change that touches no call site.

## Considered options

- **Local price table vs. a pricing library (`tokencost` / `litellm`) vs. a billing gateway** — chose the local table. A library only offloads *freshness* for mainstream ids; it is a bundled JSON snapshot, not a live feed, and would still miss this app's bleeding-edge ids (`claude-haiku-4-5`, `voyage-code-3`), so the local override and fail-loud path are needed either way. `litellm` is a heavy dependency pulled in purely for a price map, overlapping the provider SDKs already present. A gateway is the only way to get cost "in the response," but at the cost of a new proxy in the request path and entanglement with the fallback logic — disproportionate for four numbers that move rarely. `price_for` keeps the library route open if maintenance ever bites.
- **Fail loud (null + warning) vs. silent default rate** — chose fail loud. The reference implementation we started from defaults unknown models to gpt-4o-mini pricing; in a multi-provider app that turns a missing entry into a silent, large under-count instead of a visible gap.
- **Price off the configured model vs. the response's model** — chose the response's model, so fallback-served calls are priced correctly rather than as the primary that was *asked* but did not answer.

## Consequences

- **Cost is an estimate, not a bill.** It will not reconcile to the cent against a provider invoice (rounding, minimum billing units, promotional pricing, cache-token discounts we do not model). The **AI Cost** glossary term names this explicitly; the figure is for relative insight, not accounting.
- **The local table is a maintenance obligation.** New or repriced models require a code change; until then their calls record `cost = null`. The warning makes that loud, and `price_for` makes the eventual swap to a library cheap.
- **Cache/discount token details are ignored for now.** Anthropic cache-read/-write and OpenAI cached-input tokens are not separately priced in phase one; the record shape can carry them later without reshaping the table contract.
