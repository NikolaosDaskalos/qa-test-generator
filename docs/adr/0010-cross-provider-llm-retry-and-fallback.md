# Retry every LLM call and fall back across providers on transient failures

## Status

accepted

Hardens the LLM call sites of the unified graph (ADR [0002](0002-intent-routed-unified-langgraph.md)): the Classifier, Planner, repository-question answerer, Code Generator, and Code Reviewer. No new glossary term — cross-provider fallback is a provider-availability mechanism, not a domain concept, so `CONTEXT.md` is unchanged. A still-failing call after retries and fallback remains a stage-scoped Run Failure exactly as before (the Code Reviewer's `reviewing`-stage failure path is unchanged); this ADR only makes that outcome far rarer.

## Context and decision

A live Coding Run failed when the Code Reviewer's Anthropic call returned a 529 `overloaded_error` *mid-stream*, after the Anthropic SDK's default `max_retries=2` was already spent — a transient capacity blip on one provider permanently failed a user-facing run. We have two providers wired (OpenAI for the Classifier/Planner/answerer, Anthropic Claude Haiku for the Code Reviewer) and they rarely degrade at the same moment, so the right fix is bounded retry **plus** cross-provider fallback on every LLM call, not just more retries on one provider.

We decided to give each of the three logical model tiers a **primary** and a cross-provider **fallback**, keeping today's primaries so normal runs are unchanged:

| Tier | Primary | Fallback | Call sites |
|---|---|---|---|
| default | `gpt-4o-mini` | `claude-haiku-4-5` | Classifier, Planner, repository-question answerer |
| strong | `gpt-4o` | `claude-sonnet-4-6` | Code Generator |
| reviewer | `claude-haiku-4-5` | `gpt-4o-mini` | Code Reviewer |

- **Retry is SDK-level, set on the model constructors.** `max_retries=3` on both `ChatOpenAI` and `ChatAnthropic` (in `app/integrations/llm.py`), using each SDK's built-in exponential backoff (~0.5–8s), then fall back. This keeps each model a `BaseChatModel`, which is load-bearing (see below). Moderate budget: enough to ride out a brief blip, capped so a degraded provider does not stall the user for ~30s before the fallback engages.

- **Fallback attaches at two different layers, because `.with_fallbacks()`/`.with_retry()` do not return a `BaseChatModel`.** `langchain.agents.create_agent(model: str | BaseChatModel, ...)` must `bind_tools` on its model, and the Classifier/Planner nodes call `.with_structured_output(...)` on theirs — both require a real `BaseChatModel`, which the wrapper Runnables (`RunnableWithFallbacks`, `RunnableRetry`) are not. So fallback is composed *after* each site's adaptation:
  - **Agent sites** (Code Reviewer, Code Generator): build a primary agent and a fallback agent via `create_agent`, then `primary_agent.with_fallbacks([fallback_agent])`. The whole bounded ReAct loop re-runs on the fallback provider, re-issuing any `web_search` calls — acceptable since it only fires on hard failure.
  - **Direct sites** (Classifier, Planner, answerer): adapt then compose — `primary.with_structured_output(X).with_fallbacks([fallback.with_structured_output(X)])` (and the analogous `.stream(...)` chain for the answerer). A shared `with_provider_fallback(primary, fallback, adapt)` helper keeps both patterns DRY.

- **Fall back on transient/availability errors only.** 529 overloaded, 429 rate-limit, timeouts, and 5xx — the cases where the other provider genuinely might succeed. Deterministic errors (400 bad-request, 401 auth, context-length, content-policy) fail fast rather than burning a second call and masking a real bug. Because `.with_fallbacks(exceptions_to_handle=...)` matches only by `isinstance` **and Anthropic surfaces 529 as the base `anthropic.APIStatusError`** (not a 5xx subclass), a precise transient-only filter needs a small predicate wrapper that re-raises non-transient errors before they reach the fallback — this is the one piece that is custom code rather than configuration.

- **Fallback is logged, not surfaced to the user.** A WARNING (`primary=… fallback=… reason=…`) when a fallback fires gives operators visibility into provider degradation via logs/Sentry; the Agent Stream vocabulary and the frontend are untouched, and the run simply succeeds via the fallback.

## Considered options

- **Cross-provider mirror vs. same-provider downgrade vs. retry-only** — chose the mirror. Same-provider downgrade (e.g. `gpt-4o → gpt-4o-mini`) does nothing when the whole provider is overloaded, which is exactly what we hit; retry-only was already in effect (SDK default) and still failed. Falling to the *other* provider is the only option that survives a single-provider outage.
- **Keep current primaries vs. consolidate on Anthropic** — kept current primaries. Each tier only gains a fallback, so normal-path behavior, prompts, and structured-output tuning are unchanged; flipping primaries would be a larger, riskier behavior change for no availability gain.
- **SDK `max_retries` vs. Runnable `.with_retry()`** — chose SDK-level. It stays a `BaseChatModel` (compatible with `create_agent` and `.with_structured_output()`), whereas `.with_retry()` returns a wrapper that neither accepts. Re-invoking the whole call on an in-band streamed error is left to the fallback instead.
- **Agent-level vs. model-level fallback for the two agents** — forced to agent-level. `create_agent` rejects a non-`BaseChatModel` model, so the fallback cannot live on the model object and must wrap the compiled agent.
- **Transient-only vs. any-exception fallback** — chose transient-only. Falling back on any exception wastes a call on errors that cannot succeed elsewhere and can silently hop providers on a malformed prompt or a content-policy refusal, hiding real bugs.
- **Log-only vs. Agent Stream event** — chose log-only. Surfacing "switched provider" to the UI needs a new stream event type and frontend handling for a condition the user does not need to act on; logs serve the operator, who does.

## Consequences

- **Every LLM call now depends on both providers' keys being valid.** A tier's fallback is unusable if the other provider's key is missing or revoked; the primary still works, but resilience silently drops to retry-only until the key is fixed.
- **Cross-provider fallback assumes tool-call and structured-output parity.** Haiku/Sonnet and `gpt-4o`/`gpt-4o-mini` all support tool calling and structured output, but a future tier whose fallback lacks parity would break on fallback rather than on the normal path — caught only when the primary is down.
- **A fallback run can cost more and run slower than the primary** (a different model, after up to ~10–15s of retry backoff, re-running the agent's tool loop). This is the deliberate price of completing the run instead of failing it.
- **New configuration knobs:** fallback model ids and `max_tokens` per tier (mirroring the existing `LLM_MODEL*` / `*_MAX_TOKENS`) and `max_retries`; `TEMPERATURE` stays `0.0` across all models.
- **One invariant:** fallback fires only on transient/availability errors; deterministic errors (4xx, context-length, content-policy) must continue to fail fast and must not hop providers.
