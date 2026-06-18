# Restore Coding Run cards from Session History references

Status: ready-for-agent
Type: AFK
User stories: (post-PRD workspace UX — durable Test-Generation Task chronology)

## What to build

Implement [ADR 0005](../adr/0005-reference-coding-runs-from-session-history.md) so Test-Generation Tasks survive reload as part of their Repository Session’s chronological conversation. Persist the user’s task in Session History with a reference to its durable Coding Run, then reconstruct the visible coding card from the current Coding Run record when history is read.

The reconstructed card must show the durable outcome appropriate to the run: active or awaiting-review state, generated patch and findings, sanitized failure, approval and pushed branch, or rejection. Do not copy mutable patch, findings, or lifecycle snapshots into Session History. Repository-question messages and their structural Repository Evidence citations remain unchanged.

## Acceptance criteria

- [ ] Starting a Test-Generation Task records the user request in its Repository Session at the correct chronological position and associates it with the created Coding Run.
- [ ] The association is durable, ownership-safe, and removed through the existing Repository Session lifecycle.
- [ ] Full Session History reads distinguish ordinary messages from coding entries and expose the data needed to render each entry without duplicating Coding Run-owned state.
- [ ] Reloading or directly opening a Repository Session reconstructs each coding card from the current durable Coding Run record in its original chronological position.
- [ ] Awaiting decision, approved, rejected, and failed Coding Runs display their latest durable patch, findings, branch/message, or sanitized failure as applicable.
- [ ] Approval or rejection updates the reloaded card through the Coding Run record rather than appending or synchronizing a duplicated Session History snapshot.
- [ ] Repository-question persistence and structural citations continue to behave as specified by ADR 0001.
- [ ] Migration, persistence, authorization, API serialization, pagination interaction, and reload rendering are covered by automated tests.

## Blocked by

- [Issue 45](45-paginated-full-session-history.md)
