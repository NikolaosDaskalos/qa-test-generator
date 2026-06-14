# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the `Status:` strings used in this repo's local-markdown issue files.

| Canonical role    | Local status      | Meaning                                                 |
|-------------------|-------------------|---------------------------------------------------------|
| `needs-triage`    | `needs-triage`    | Maintainer evaluation is required                       |
| `needs-info`      | `needs-info`      | More information is required from the reporter          |
| `ready-for-agent` | `ready-for-agent` | Fully specified and ready for autonomous implementation |
| `ready-for-human` | `ready-for-human` | Human implementation is required                        |
| `wontfix`         | `wontfix`         | The work will not be actioned                           |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), set the issue's `Status:` line to the corresponding local status.

## Repo-specific status

In addition to the five canonical roles, this repo uses one extra terminal status:

| Local status | Meaning                       |
|--------------|-------------------------------|
| `completed`  | Implemented and verified      |

`completed` is outside the canonical triage state machine — the `triage` skill won't drive issues into it automatically. Use it as a manual done-marker once a slice is shipped and verified.
