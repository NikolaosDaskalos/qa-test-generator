# Create immutable Repository Sessions with bounded Session History

Status: ready-for-agent
Type: AFK
User stories: 18-22

## What to build

Replace Search Session as the canonical workflow with a Repository Session owned by one user and permanently bound to one Repository. Persist each user and assistant exchange as Session History and remove the duplicate serialized memory copy.

The Repository binding must be enforced for the lifetime of the session, and downstream question and task workflows must receive at most the six most recent history messages.

## Acceptance criteria

- [ ] An authenticated Repository owner can create a Repository Session by supplying a ready Repository identity.
- [ ] A Repository Session has a required Repository foreign key and cannot be reassigned after creation.
- [ ] Access to Repository Sessions and Session History enforces user ownership.
- [ ] Each exchange is persisted as ordered Session History without maintaining a duplicate JSON memory field.
- [ ] History loading for reformulation and planning returns at most the six most recent messages in chronological order.
- [ ] Working with another Repository requires creation of a new Repository Session.
- [ ] Migrations preserve required relationships and define appropriate cascade behavior.
- [ ] Route, persistence, model, and migration tests cover ownership, immutable binding, history ordering, bounded history, and removal of duplicate memory.

## Blocked by

- [01 - Register and clone a GitHub Python Repository](01-register-clone-github-python-repository.md)

