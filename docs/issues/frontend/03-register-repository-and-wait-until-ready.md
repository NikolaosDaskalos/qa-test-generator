# Register a Repository and wait until it is ready

Status: completed
Type: AFK
User stories: frontend bare-minimum copilot

## What to build

Let the user connect a new GitHub Python Repository from the Copilot page and watch it become
usable. A creation form collects the repository URL, a GitHub token, and a token expiration; on
submit the backend accepts the request and begins clone/index processing in the background while
the repository starts in a non-ready status.

Because indexing has no stream, the page polls the repository's status until it reaches `ready` or
`failed`, updating the displayed status live. When the repository becomes `ready` it is available
for selection and chatting; when it fails, the failure reason is shown. This polling is specific to
repository indexing and is unrelated to the Agent Stream (which is never polled).

## Acceptance criteria

- [x] A creation form submits repository URL, GitHub token, and token expiration and handles the accepted (async) response.
- [x] After creation the page polls the repository's status and reflects status transitions live without a manual refresh.
- [x] Polling stops when the repository reaches `ready` or `failed`.
- [x] A newly ready repository becomes selectable/usable; a failed one shows its failure reason.
- [x] Validation and backend errors on creation are surfaced to the user rather than failing silently.

## Blocked by

- [02 - List and select a Repository with live status](02-list-and-select-repository.md)
