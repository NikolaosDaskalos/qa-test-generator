# List and select a Repository with live status

Status: ready
Type: AFK
User stories: frontend bare-minimum copilot

## What to build

Let the user choose which Repository to work with on the Copilot page. Populate a repository
selector from the authenticated user's repositories, showing each repository's processing status
(pending, cloning, indexing, ready, failed) so the user can tell at a glance which repositories are
usable. Selecting a repository sets it as the active repository for the rest of the page.

Only a repository that has reached `ready` may be used for chatting; selecting a not-yet-ready or
failed repository keeps the chat area disabled with a clear indication of why. A failed repository
surfaces its failure reason.

## Acceptance criteria

- [ ] The repository selector lists the authenticated user's repositories fetched from the backend.
- [ ] Each repository shows its current status, and a failed repository shows its failure reason.
- [ ] Selecting a repository sets it as the active repository for the page.
- [ ] The chat area is enabled only when the active repository's status is `ready`; otherwise it is disabled with an explanation.
- [ ] An empty repository list renders a sensible empty state rather than an error.

## Blocked by

- [01 - Regenerate the API client and scaffold the single-page Copilot shell](01-regenerate-client-and-scaffold-copilot-shell.md)
