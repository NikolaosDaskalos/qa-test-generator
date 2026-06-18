# Automatically title and order Repository Sessions by activity

Status: ready-for-agent
Type: AFK
User stories: (post-PRD workspace UX — recognizable and activity-ordered Repository Sessions)

## What to build

Create blank Repository Sessions with the visible title “New session.” On the first user request, replace that placeholder with a short deterministic title derived from the normalized request text without another model call or naming dialog. Keep the derived title stable on later turns.

Treat user messages and resolved Coding Run decisions as Repository Session activity. Update the session activity time and list sessions newest-activity-first within their Repository so the sidebar reflects where the user most recently worked. Manual rename and delete controls are outside this slice.

## Acceptance criteria

- [ ] A newly created Repository Session is persisted and displayed as “New session.”
- [ ] Its first non-empty user request produces a deterministic, normalized title of at most 60 display characters without an LLM call.
- [ ] Later requests do not overwrite the derived title.
- [ ] Sending a user request updates Repository Session activity and moves it to the top of its Repository’s session list.
- [ ] Resolving a Coding Run approval or rejection updates Repository Session activity without changing an established title.
- [ ] Repository Sessions are returned and rendered newest-activity-first with deterministic tie-breaking.
- [ ] Reloading or directly opening the session URL preserves the title and ordering.
- [ ] Repository question, Test-Generation Task, decision, and stable-title behavior are covered across persistence, API, and UI tests.

## Blocked by

- [Issue 43](43-deep-linked-repository-session-navigation.md)
