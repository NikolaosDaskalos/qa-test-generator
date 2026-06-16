# Allow new Test Files only in existing test roots

Status: completed
Type: AFK
User stories: 41-46

## What to build

Extend Test Patch validation to permit new Python Test Files when, and only when, they are created beneath a test root that already exists in the Repository. The validation must recognize the Repository's established test structure without allowing the generator to invent one.

This behavior must use the same checkout confinement, symlink, language, and application-file protections as modifications to existing Test Files.

## Acceptance criteria

- [x] Existing Repository test roots named `tests` or `test` are discovered before proposals are written.
- [x] A new `.py` Test File beneath an existing test root is accepted.
- [x] A new file outside existing test roots is rejected even when its name resembles a test.
- [x] A proposal that creates a new top-level or nested test root is rejected.
- [x] Path traversal, absolute paths, symlinks, non-Python files, and source-file replacement remain rejected.
- [x] Validation failure records a `validation` Run Failure with a sanitized reason and leaves no unapproved file changes.
- [x] Temporary-checkout tests cover accepted nested test paths and every rejected new-file category.

## Blocked by

- [09 - Generate canonical diffs for existing Test Files](09-generate-canonical-test-patch.md)

