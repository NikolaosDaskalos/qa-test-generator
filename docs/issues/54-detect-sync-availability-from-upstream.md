# Detect Sync Availability from the upstream default branch

Status: ready-for-agent
Type: AFK
User stories: (new — Sync Availability; extends US 10-17 Repository Synchronization)

## What to build

Add a read-only background loop that surfaces **Sync Availability**: the owner learns, without asking, that a Repository's remote default-branch head has advanced beyond its indexed commit, so the existing manual **Synchronization Request** flow gets a "sync now" affordance. Per ADR [0008](../adr/0008-poll-upstream-for-sync-availability-not-auto-sync.md), this detects only — it never runs Repository Synchronization, never opens the checkout, and never advances the indexed commit.

Detection uses `git ls-remote` through the existing `GitCommands` credential boundary (askpass, token redaction, sanitized `GitError`). Because `ls-remote` reads the remote ref list against the canonical URL and does not touch the working tree, detection is **not** a Checkout Operation and never engages the ADR [0007](../adr/0007-single-writer-checkout-claim-per-repository.md) marker.

A nullable `latest_upstream_commit_sha` column on `Repository` records the last observed remote head; `RepositoryPublic` exposes a derived `sync_available` boolean (`latest_upstream_commit_sha is not None and latest_upstream_commit_sha != indexed_commit_sha`). The frontend reads it through the Repository status endpoint it already polls — no websockets.

The loop lives in the FastAPI `lifespan` (create on startup, `cancel()` on shutdown) and offloads each tick's blocking subprocess + sync-DB work via `anyio.to_thread.run_sync`. The per-repo tick is a `RepositoryService` method composed by a module-level function mirroring `process_repository`, so it is unit-testable with the existing fake-store / fake-Git pattern.

## Acceptance criteria

- [ ] A background loop, started and gracefully cancelled by the FastAPI `lifespan`, polls upstream on a configurable interval (default 60s).
- [ ] Detection uses `git ls-remote` via `GitCommands` with the decrypted Repository Credential; it never opens or mutates the local checkout (not a Checkout Operation) and never engages the ADR 0007 marker.
- [ ] Each tick's blocking work (`ls-remote` subprocess and synchronous DB access) runs via `anyio.to_thread.run_sync`; no blocking call runs directly on the event loop.
- [ ] The loop polls only `status == ready` repositories and skips repositories whose `token_expiration_date` is already past.
- [ ] The observed remote head is persisted to a new nullable `Repository.latest_upstream_commit_sha` column (Alembic migration included).
- [ ] `RepositoryPublic` exposes a derived `sync_available` boolean; it is `true` exactly when a non-null observed upstream head differs from `indexed_commit_sha`.
- [ ] A failed poll (network error, revoked/expired token, deleted remote) is swallowed and logged; it never mutates `status` or `failed_reason`, never calls `repository_store.fail()`, and leaves `latest_upstream_commit_sha` at its last value.
- [ ] An exception in one repository's tick does not stop the loop or affect other repositories.
- [ ] Running Repository Synchronization still happens only via an explicit, user-initiated Synchronization Request; nothing in this loop triggers it.
- [ ] The Repository Credential is never exposed in logs or error messages from detection.
- [ ] Tests use the fake-store / fake-Git pattern (no network) and cover: remote moved → `latest_upstream_commit_sha` updated and `sync_available` true; remote unchanged → `sync_available` false; `ls-remote` failure → no mutation to `status`, `failed_reason`, or the stored head; expired-token and non-ready repositories skipped; and that detection never invokes Repository Synchronization or the checkout.

## Notes / limits

- **Single process only.** Under `uvicorn --workers N` each worker runs its own loop (N× `ls-remote` calls, racing column writes). Consistent with ADR 0007's single-process demo stance; out of scope to solve here.
- Token-expiry feedback remains the credential-update flow's concern (issue [42](42-repository-status-and-credential-update.md)), not this loop. A quietly expired token simply makes the hint go stale.

## Related

- Refines the Out-of-Scope boundary alongside issue [03](03-incrementally-synchronize-repository-evidence.md) (manual Repository Synchronization).
- Frontend surfacing of the `sync_available` affordance is a follow-up on the workspace status views (issues [42](42-repository-status-and-credential-update.md)).
