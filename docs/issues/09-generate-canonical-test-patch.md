# Generate canonical diffs for existing Test Files

Status: ready-for-agent
Type: AFK
User stories: 38-40, 42-45, 54

## What to build

Extend the Coding Run through generation for existing Test Files. Restore the shared checkout to the indexed default-branch commit, create a unique non-default temporary branch, ask the generator for structured complete-file proposals, validate them, write them, and derive the canonical unified diff with Git.

The LLM must not author or apply an arbitrary unified diff, and proposals must not modify application code.

## Acceptance criteria

- [ ] Generation starts from a clean checkout restored to the Repository's indexed commit on a uniquely named non-default temporary branch.
- [ ] The generator receives the Test-Generation Task and validated Repository Evidence, without unrestricted shell or filesystem tools.
- [ ] Generator output is a structured collection of complete file paths and complete contents rather than diff text.
- [ ] Existing recognized Python Test Files may be modified.
- [ ] Absolute paths, traversal outside the checkout, symlink targets, non-Python files, and application or source files are rejected before writing.
- [ ] The backend writes only validated Test Files and obtains the displayed Test Patch from Git.
- [ ] The Coding Run persists generated file proposals and the canonical diff and streams patch progress and the final diff.
- [ ] Tests cover clean branch preparation, structured generation, each rejection boundary, canonical diff generation, and generation or validation Run Failure.

## Blocked by

- [08 - Plan Test-Generation Tasks from Repository Evidence](08-plan-test-generation-from-evidence.md)

