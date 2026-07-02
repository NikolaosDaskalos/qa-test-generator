# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the GitHub labels used in this repo's issues. Apply them with `gh issue edit <number> --add-label <label>`.

| Canonical role    | GitHub label      | Meaning                                                 |
|-------------------|-------------------|---------------------------------------------------------|
| `needs-triage`    | `needs-triage`    | Maintainer evaluation is required                       |
| `needs-info`      | `needs-info`      | More information is required from the reporter          |
| `ready-for-agent` | `ready-for-agent` | Fully specified and ready for autonomous implementation |
| `ready-for-human` | `ready-for-human` | Human implementation is required                        |
| `wontfix`         | `wontfix`         | The work will not be actioned                           |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), add the corresponding GitHub label to the issue. If a label does not yet exist in the repo, create it once with `gh label create <label> --description "..."`.

## Repo-specific status

In addition to the five canonical roles, this repo uses one extra terminal status. Because GitHub closes shipped work, mark done issues by closing them:

| Status      | How to apply                  | Meaning                       |
|-------------|-------------------------------|-------------------------------|
| `completed` | `gh issue close <number>`     | Implemented and verified      |

`completed` is outside the canonical triage state machine — the `triage` skill won't drive issues into it automatically. Close the issue as a manual done-marker once a slice is shipped and verified.
