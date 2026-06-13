# Delete Repository state with persisted failure details

Status: ready-for-agent
Type: AFK

## What to build

Make Repository deletion run in this order: delete the local checkout, delete
the Repository's vectors, then delete the PostgreSQL Repository record.

If any stage fails, preserve the PostgreSQL Repository record, set its status
to `failed`, and populate a sanitized, bounded failure reason. It is acceptable
for PostgreSQL to remain temporarily out of sync with the local checkout and
vector database after a failure.

The design was validated in the Repository deletion prototype. If PostgreSQL
deletion or commit fails, roll back that transaction before reloading the
Repository and persisting its failure state in a new transaction. Configure
the SourceDocument relationship so PostgreSQL can apply the existing
`ON DELETE CASCADE` constraint instead of SQLAlchemy setting non-null
`repository_id` values to `NULL`.

## Acceptance criteria

- [ ] Successful deletion removes the local Repository checkout, its vectors, the PostgreSQL Repository row, and its SourceDocuments, in that order.
- [ ] PostgreSQL deletes SourceDocuments through the existing database cascade without attempting to set `source_document.repository_id` to `NULL`.
- [ ] A local checkout deletion failure leaves vectors and relational records intact and persists Repository status `failed` with a sanitized failure reason.
- [ ] A vector deletion failure after local cleanup leaves the relational records intact and persists Repository status `failed` with a sanitized failure reason.
- [ ] A PostgreSQL deletion or commit failure after external cleanup is rolled back before the Repository is reloaded and updated to `failed`.
- [ ] Failure reasons are bounded and do not expose Repository Credentials or provider internals.
- [ ] The delete endpoint reports the failure while leaving the persisted Repository failure state inspectable.
- [ ] Tests cover successful cascading deletion and failures during local, vector, and PostgreSQL cleanup using real ORM behavior where required.

## Blocked by

None - can start immediately
