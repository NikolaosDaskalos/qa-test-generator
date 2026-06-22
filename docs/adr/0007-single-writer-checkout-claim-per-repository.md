# Single-writer Checkout Operation claim per Repository, orthogonal to status

## Status

accepted

Informs issues [22](../issues/22-incrementally-synchronize-repository-evidence.md) (background Repository Synchronization) and [23](../issues/23-serialize-and-cancel-active-coding-runs-safely.md) (serialize and cancel active Coding Runs). Introduces the **Checkout Operation** glossary term in `CONTEXT.md`.

## Context and decision

The backend already serves different Repositories and different users concurrently: routes are synchronous `def` handlers running in FastAPI's anyio threadpool, repository cloning and indexing is offloaded to a FastAPI background task, and per-Repository conflicts are surfaced as `409`s (`DuplicateRepository`, `RepositoryProcessing`, `RepositoryNotReady`). The desire to "support async operations" turned out to mean **per-Repository mutual exclusion with cross-Repository concurrency**, not an asyncio rewrite. We explicitly rejected converting to `async def` + async SQLAlchemy + `graph.astream`: it touches every layer to lift a ~40-thread ceiling a course demo never reaches, and the glossary already nails **Agent Stream** to a *synchronous* SSE response.

The real gap is that three operations mutate a Repository's single local checkout — **clone/index**, **Repository Synchronization** (#22), and a **Coding Run** (#23) — and must not overlap on the same Repository, or two working-tree/branch manipulations mix changed files together. Repository questions are read-only against the Weaviate vector store and touch no checkout, so they must stay concurrent.

We decided on a **single-writer claim per Repository over the checkout**:

- **The checkout is the exclusion unit.** At most one Checkout Operation runs per Repository at a time; a concurrent request for the same Repository is rejected with `409`. A different Repository proceeds independently. Questions never engage the exclusion.
- **A dedicated atomic marker on the Repository row, orthogonal to `status`.** The claim is a nullable `active_checkout_operation` marker acquired by a conditional compare-and-swap (`UPDATE … WHERE marker IS NULL`, reject if zero rows affected). It is **not** the `status` enum, because `status == ready` gates question availability (`create_session` → `RepositoryNotReady`); a Coding Run must hold the checkout while leaving `ready` intact so questions keep working.
- **Every Checkout Operation claims it**, clone/index included, so the invariant stays clean: *Checkout Operation in progress ⟺ marker set*. For clone/index this is belt-and-suspenders (its not-`ready` status already blocks sync and runs), accepted for uniformity.
- **The marker is held across the human-review pause.** A Coding Run pauses at the HITL `interrupt` after escalating a patch, with no open connection during the wait; the temp branch and working-tree changes persist, so the claim must survive until the decision resolves (approve → commit/push/PR, or reject → discard).
- **Released in `finally` on any terminal outcome or generation-stream disconnect.** Sync streaming surfaces client disconnect as `GeneratorExit` at the next `yield`; cleanup (record `RunFailure`, discard working tree, restore the indexed commit, delete the temp branch, release the marker) runs in `finally`. Cancellation is cooperative — an in-flight model call finishes before the abort lands at the next stage boundary.
- **No TTL; stuck markers cleared on startup.** In a single-process demo no claim legitimately survives a restart, so startup clears markers and #23's cleanup is idempotent. A paused-but-abandoned run holds the repo until the next decision or a restart, rather than auto-expiring.

## Considered options

- **Per-Repository serialization vs. asyncio rewrite** — chose serialization plus the existing background-task model. The rewrite (async routes/DB/graph) only pays off under dozens of simultaneous long operations, which contradicts the demo's "concurrency out of scope" stance and the synchronous Agent Stream contract.
- **One checkout writer vs. independent sync/run locks** — chose a single writer over the checkout. Separate locks would let a Synchronization and a Coding Run overlap on the same working tree and `git checkout`, which is the exact file-mixing we set out to prevent. This generalizes the prior "at most one active Coding Run" rule to the whole checkout.
- **Dedicated marker vs. reusing `status` vs. deriving from records vs. in-process lock** — chose a dedicated atomic marker orthogonal to `status`. Reusing `status` would flip a repo out of `ready` during a run and break concurrent questions. Deriving "busy" from active sync/run records needs a `SELECT … FOR UPDATE` over two tables on every claim for the same effect. An in-process `threading.Lock` registry works only in the single demo process, evaporates on restart, and adds a lock-lifecycle map; the DB marker is race-free across threadpool threads (and processes) and is the single claim point.
- **Hold across HITL pause vs. release while awaiting decision** — chose to hold. Releasing during the unconnected human-review gap would let a sync or new run clobber the pending patch's branch. Cost: while a patch awaits a decision, sync and new runs on that repo are rejected with `409`, and an abandoned paused run holds the repo until a restart.
- **No TTL vs. lease/auto-expiry** — chose no TTL. A lease invites releasing a still-live claim mid-operation; in a single-process demo, startup clearing plus idempotent cleanup recovers every stuck-marker case (crash, or human never returns) without that risk.
