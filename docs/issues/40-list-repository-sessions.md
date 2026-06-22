# List Repository Sessions, optionally filtered by Repository

Status: completed
Type: AFK
User stories: none

## What to build

Add a `GET /sessions` endpoint that returns the caller's Repository Sessions as a
paginated, counted collection. A `repository_id` query parameter is an optional
filter: when omitted the endpoint lists all of the caller's sessions across every
Repository; when supplied it lists only the sessions bound to that Repository.

Results are scoped to the caller by session ownership, with the same superuser
bypass the Repository list uses (a superuser sees every session). Sessions are
ordered most-recently-changed first, by the session row's `updated_at` descending
with `id` as a deterministic tiebreaker for stable paging. Pagination mirrors the
Repository list endpoint: `skip` (default 0) and `limit` (default 100), with a
total `count` of all matching sessions independent of the page window.

When `repository_id` is supplied it is validated like a read, not a write: a
missing Repository is a 404 and a Repository the caller does not own is a 403
(superuser bypassed). The readiness check that gates session creation is
deliberately NOT applied here — listing the sessions of a Repository that is still
indexing or has failed must still work. The unfiltered call validates nothing.

The existing `RepositorySessionPublic` schema is reused unchanged (it already
carries `repository_id`); only a new collection wrapper carrying `data` and
`count` is introduced. No repository name is denormalized onto the response.

## Acceptance criteria

- [x] `GET /sessions` returns the caller's Repository Sessions wrapped as `{ data, count }`, where `count` is the total of all matching sessions regardless of pagination.
- [x] `repository_id` is an optional query parameter; omitting it lists sessions across all of the caller's Repositories, supplying it restricts results to that Repository.
- [x] Results are scoped by session ownership, with a superuser bypass that returns every matching session.
- [x] Sessions are ordered by `updated_at` descending with `id` as a tiebreaker, and `skip`/`limit` (defaults 0/100) page the results.
- [x] A supplied `repository_id` is validated: 404 when the Repository does not exist, 403 when the caller does not own it (superuser bypassed).
- [x] A supplied `repository_id` for a not-ready Repository still lists its sessions — no readiness conflict is raised on this read path.
- [x] `RepositorySessionPublic` is unchanged; the create endpoint's response shape is unaffected.
- [x] Route, service, and persistence tests cover ownership scoping, the superuser bypass, the optional filter (present and absent), repository validation (404/403, readiness not enforced), ordering, and pagination with count.

## Blocked by

- None - can start immediately
