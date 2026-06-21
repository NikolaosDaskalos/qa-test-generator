# Poll upstream to surface Sync Availability, never to auto-synchronize

## Status

accepted

Introduces the **Sync Availability** glossary term in `CONTEXT.md`. Refines the Out-of-Scope boundary in the PRD ("Automatic synchronization through schedules, polling, webhooks, or push events") without reversing it, and respects the single-writer Checkout Operation claim of ADR [0007](0007-single-writer-checkout-claim-per-repository.md). Informs issue [54](../issues/54-detect-sync-availability-from-upstream.md).

## Context and decision

We want a Repository's owner to learn, without manually asking, that its remote default branch has advanced beyond the indexed commit — so the "always in sync" experience becomes real. The tempting implementation (a generic `asyncio` + `httpx` poller that runs the sync when it sees a new commit) is exactly the **automatic synchronization through polling** the PRD lists as Out of Scope, and it collides with ADR 0007: Repository Synchronization is a **Checkout Operation** guarded by a single-writer claim, so an unattended timer-driven sync would race the claim — and lose, with a silent `409`, whenever a Coding Run holds the checkout across its human-review pause.

We decided to split *detection* from *synchronization* and ship only detection:

- **Poll to notice, never to act.** A background loop observes the remote default-branch head and records it; it never runs Repository Synchronization, never opens the checkout, and never advances the indexed commit. Synchronization stays a user-initiated **Synchronization Request**. The new signal is **Sync Availability**, surfaced as a derived boolean on the existing Repository read model the frontend already polls.
- **`git ls-remote` over the GitHub REST API.** Detection reuses the existing `GitCommands` credential boundary (askpass, token redaction, sanitized `GitError`). Critically, `ls-remote` reads the remote ref list against the canonical URL and **does not touch the working tree**, so detection is provably *not* a Checkout Operation and never engages the ADR 0007 marker. It also honors GitHub Enterprise hosts for free and carries none of the REST rate-limit accounting that the ETag/304 dance exists to manage.
- **Persist the observed head; derive the boolean.** A nullable `latest_upstream_commit_sha` column on `Repository` holds the last observed remote head (a metadata write, not a Checkout Operation). `sync_available` is derived as `latest_upstream_commit_sha is not None and latest_upstream_commit_sha != indexed_commit_sha`. The signal survives restart and is inspectable.
- **Strictly additive: detection can never degrade the question path.** A failed poll (network blip, revoked or expired token, deleted remote) is swallowed and logged. It must never call `repository_store.fail()` or otherwise mutate `status`/`failed_reason`, because `status == ready` gates question availability (ADR 0007); the worst outcome of a bad poll is a stale hint. The loop polls only `ready` repositories and skips those whose token has already expired.
- **Async lifespan task, blocking work offloaded.** The loop lives in the FastAPI `lifespan` (create task on startup, `cancel()` on shutdown). Because `ls-remote` is a subprocess and the DB layer is synchronous SQLAlchemy, each tick's work runs through `anyio.to_thread.run_sync` — the same threadpool seam ADR 0007's synchronous routes already use — so no blocking call ever lands on the event loop. The tick logic is a `RepositoryService` method composed by a module-level function mirroring `process_repository`, unit-testable with the existing fake-store / fake-Git pattern; the async loop is dumb pacing glue.

## Considered options

- **Detect-and-notify vs. detect-and-auto-sync** — chose notify only. Auto-sync reverses a documented Out-of-Scope decision and forces a design for how a timer-driven writer interacts with the single-writer checkout claim and the indefinite HITL pause. Notification delivers the "always in sync" feel as *awareness* without an unattended process mutating a shared working tree and Weaviate tenant.
- **`git ls-remote` vs. PyGithub vs. hand-rolled `httpx`** — chose `ls-remote`. Hand-rolled `httpx` is forbidden by ADR 0006 ("hand-rolled HTTP clients are not used"). PyGithub (adopted in 0006) would work but adds REST rate-limit accounting multiplied across every polled repo. `ls-remote` reuses the hardened Git credential path, is unambiguously read-only/not-a-Checkout-Operation, and needs none of the ETag machinery that exists only to economize REST quota.
- **Persisted column vs. in-memory map** — chose a persisted nullable column. It matches the existing `indexed_commit_sha` pattern on the same row, rides the read model the frontend already polls, and survives restart instead of going dark until the next tick. The in-memory dict is less code but trades it for restart amnesia and a singleton threaded into the request path anyway.
- **Async task + `to_thread` vs. a dedicated daemon thread** — chose the async lifespan task. It keeps the idiomatic FastAPI create/cancel skeleton and reuses the threadpool seam the app already relies on, rather than introducing a second concurrency primitive (raw thread + stop-Event) for a single background loop.

## Consequences

- One Alembic migration adds `latest_upstream_commit_sha`; the column is meaningless until the loop runs once.
- **Single process only.** Under `uvicorn --workers N` each worker runs its own loop, producing N× the `ls-remote` calls and racing writes to the column. This is consistent with ADR 0007's single-process demo stance and is an accepted limit, not a bug to solve here.
- A quietly expired token makes the hint go stale with no explicit "your token died" nudge from this feature; token health remains the concern of the credential-update flow, not the poller.
- The one rule that must be held in review and tests: **no blocking call (subprocess or DB) ever runs directly in the `async def` loop body — always via `to_thread`**, and **a poll failure never mutates `status`**.
