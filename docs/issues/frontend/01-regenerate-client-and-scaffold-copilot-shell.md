# Regenerate the API client and scaffold the single-page Copilot shell

Status: completed
Type: AFK
User stories: frontend bare-minimum copilot

## What to build

Bring the generated frontend API client in sync with the current backend and stand up the single
page that the whole copilot UI will live on. Regenerating the client surfaces the repository and
session services the UI needs and removes services for routes the backend no longer exposes.

Run the existing client-generation script so the generated client gains the repository and session
operations (create/list/get repository, create session, stream questions, history, run, patch) and
drops the now-absent `items` service. Because the regenerated client no longer exports an items
service, the template's items screens and any other scaffolding the project chose to remove must go
or the build breaks. Per the approved plan, the template `items`, `admin`, and `settings` screens,
their components, and their sidebar entries are stripped, and the existing dashboard index route is
replaced with an empty Copilot page shell: a region for repository selection/creation and a region
for the chat, both still inert. Login and signup continue to work unchanged.

This is an enabling tracer: a logged-in user lands on the Copilot shell and the project builds and
lints cleanly.

## Acceptance criteria

- [x] The generated client is regenerated from the current backend and exposes the repository and session operations; the dead items service no longer exists in the client.
- [x] Template items, admin, and settings routes/components and their sidebar entries are removed, and no remaining import references the deleted code.
- [x] The authenticated index route renders a Copilot shell with a repository area and a chat area (no behavior yet).
- [x] An unauthenticated visitor is still redirected to login; login and signup still succeed.
- [x] `build` and `lint` pass.

## Blocked by

- None - can start immediately
