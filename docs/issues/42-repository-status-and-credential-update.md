# Expose Repository status and credential updates in the workspace

Status: ready-for-agent
Type: AFK
User stories: (post-PRD workspace UX — Repository processing visibility and credential maintenance)

## What to build

Give a selected Repository a status/details view in the main workspace. Pending, cloning, and indexing Repositories report live progress until they become ready or failed. A failed Repository presents its sanitized failure reason. Repository Sessions remain unavailable until the Repository is ready.

Allow the owner to update the Repository Credential from this details view for any Repository. Updating the credential may update its optional numeric expiration period, but it must not change or restart the Repository’s processing status. Retry processing is explicitly outside this slice because no retry API exists.

## Acceptance criteria

- [ ] Selecting a non-ready Repository opens a clear status/details view instead of an enabled chat composer.
- [ ] Pending, cloning, and indexing statuses refresh until the Repository reaches ready or failed, then polling stops.
- [ ] A failed Repository displays its sanitized failure reason and does not offer a retry-processing action.
- [ ] New Repository Session creation is unavailable unless the selected Repository is ready.
- [ ] Every accessible Repository exposes an Update token action in the main details view rather than cluttering the sidebar.
- [ ] Updating the Repository Credential supports an optional positive expiration period in days and leaves the Repository status unchanged.
- [ ] Ready, processing, failed, credential-success, credential-validation-error, and unchanged-status behavior are covered end to end.

## Blocked by

- [Issue 41](41-copilot-repository-empty-state.md)
