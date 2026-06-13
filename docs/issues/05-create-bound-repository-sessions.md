# Create immutable Repository Sessions with bounded Session History

Status: completed
Type: AFK
User stories: 18-22

## What to build

Replace Search Session as the canonical workflow with a Repository Session owned by one user and permanently bound to one Repository. Persist each user and assistant exchange as Session History and remove the duplicate serialized memory copy.

The Repository binding must be enforced for the lifetime of the session, and downstream question and task workflows must receive at most the six most recent history messages.

## Acceptance criteria

- [x] An authenticated Repository owner can create a Repository Session by supplying a ready Repository identity.
- [x] A Repository Session has a required Repository foreign key and cannot be reassigned after creation.
- [x] Access to Repository Sessions and Session History enforces user ownership.
- [x] Each exchange is persisted as ordered Session History without maintaining a duplicate JSON memory field.
- [x] History loading for reformulation and planning returns at most the six most recent messages in chronological order.
- [x] Working with another Repository requires creation of a new Repository Session.
- [x] Migrations preserve required relationships and define appropriate cascade behavior.
- [x] Route, persistence, model, and migration tests cover ownership, immutable binding, history ordering, bounded history, and removal of duplicate memory.

## Blocked by

- [01 - Register and clone a GitHub Python Repository](01-register-clone-github-python-repository.md)
