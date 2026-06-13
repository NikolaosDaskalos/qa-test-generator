# Register and clone a GitHub Python Repository

Status: completed
Type: AFK
User stories: 1-8

## What to build

Allow an authenticated user to register a public or private GitHub Repository with a mandatory Repository Credential. Registration must return without waiting for clone and initial processing, expose useful processing states, reject non-GitHub providers, and report sanitized failures without exposing the credential.

This slice establishes the Repository checkout and authentication boundary used by indexing, synchronization, and Approval.

## Acceptance criteria

- [x] Registration accepts supported GitHub HTTPS or SSH URL forms and stores one canonical, credential-free Repository URL.
- [x] A Repository Credential is required for public and private Repository registration and is stored through the existing encrypted credential boundary.
- [x] GitLab, Bitbucket, custom hosts, malformed URLs, and duplicate Repository registrations for the same user are rejected.
- [x] Registration schedules clone and processing as a FastAPI background task and returns an accepted response without waiting for completion.
- [x] Clone, fetch-ready checkout information, detected default branch, and processing status are persisted for the Repository owner.
- [x] Repository status exposes pending, cloning, indexing, ready, and failed outcomes through the Repository lookup endpoint.
- [x] Provider and Git failures are sanitized and never expose the Repository Credential in API responses or logs.
- [x] Route and service tests cover authentication, ownership, URL validation, background scheduling, status transitions, and sanitized failures.

## Blocked by

None - can start immediately

