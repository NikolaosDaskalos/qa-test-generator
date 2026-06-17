# Concentrate Repository processing state behind named transitions

Status: completed
Type: AFK
User stories: 01-02 (refactor — prerequisite for the Repository Synchronization work in issue 03 / US 10-17)

## What to build

`process_repository` drives the Repository through its processing lifecycle as a
procedural sequence: it names raw statuses inline (`update_status(repository,
RepositoryStatus.cloning)`, then `…indexing`), mutates checkout fields directly on
the model (`repository.local_path = …`, `repository.default_branch = …`),
publishes the indexed commit via `mark_ready`, and on failure stamps a
credential-sanitized reason. The status moves, checkout-field writes, indexed-
commit publication, and failure sanitization are spread through the orchestration,
and `_sanitized_failure` is a free function shared with `delete_repository`. This
matters now because the Repository Synchronization work (issue 03) widens this
same method with file-level indexed-commit rules, so the state moves should be
concentrated first.

Concentrate the **state moves** behind named transitions on `RepositoryStore`
(which already owns `update_status` / `mark_ready`): a begin-cloning transition, a
record-checkout transition that writes `local_path` and `default_branch` (so they
stop being mutated directly on the model in the service), a begin-indexing
transition, a mark-ready transition that publishes the indexed commit, and a fail
transition that performs the credential-sanitized redaction itself. `process_
repository` becomes an orchestrator that drives the Git clone/checkout and
ingestion and calls these named transitions; the clone/checkout/ingest
orchestration is deliberately *not* pulled into the store, because incremental
Synchronization needs a different orchestration over the same transitions.
`delete_repository` calls the same fail transition instead of the free
`_sanitized_failure` function, so the redaction rule lives with the state move it
always accompanies.

End to end, behavior is unchanged: a Repository still moves pending → cloning →
indexing → ready (or → failed with a sanitized, credential-free reason), still
records `local_path` / `default_branch` from the checkout, still publishes the
indexed commit atomically on mark-ready, and an empty index still fails the run.

## Acceptance criteria

- [x] `RepositoryStore` exposes named processing transitions (begin-cloning,
      record-checkout writing `local_path`/`default_branch`, begin-indexing,
      mark-ready publishing the indexed commit, fail with credential-sanitized
      reason); `process_repository` calls them instead of naming raw statuses or
      mutating checkout fields on the model.
- [x] Credential-sanitized failure redaction lives in the fail transition; both
      `process_repository` and `delete_repository` use it (the standalone
      `_sanitized_failure` free function is gone or reduced to the transition's
      internal helper).
- [x] The clone/checkout/ingest orchestration stays in the service (not pulled
      into the store), so incremental Synchronization can reuse the transitions.
- [x] The transitions are unit-tested directly against a store/fake (each status
      move, checkout-field write, atomic indexed-commit publication, sanitized
      failure redaction) without running a real clone or ingest.
- [x] Behavior is preserved: the pending→cloning→indexing→ready/failed sequence,
      checkout-field capture, atomic indexed-commit publication, and empty-index
      failure all still hold; the backend suite passes excluding known
      environmental/pre-existing failures.

## Blocked by

None - can start immediately. Should land before issue 03 (Repository
Synchronization), which widens the same processing method and is recorded as
blocked by this issue.
