# Reference Coding Runs from Session History

## Status

accepted

## Context and decision

Test-Generation Tasks and their review, failure, approval, or rejection results must remain visible in their original position after a Repository Session is reopened. Session History will persist the user's request and a reference to the durable Coding Run, then the read model will reconstruct the coding card from the Coding Run record. It will not duplicate mutable patch, review, or status snapshots inside Session History; this preserves one record of truth and prevents reloaded conversations from presenting stale run state.

## Considered options

- **Reference the Coding Run** — chosen because Coding Run already owns its lifecycle, patch, findings, and decision outcome. Session History owns chronology, while the reference connects the two records without duplicating their data.
- **Snapshot every coding state into Session History** — rejected because approval and rejection can change after the first review result. Keeping snapshots synchronized would create two records of truth or require append-only lifecycle events and more complex reconstruction.
