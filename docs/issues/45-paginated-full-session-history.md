# Display paginated full Session History while bounding AI context

Status: ready-for-agent
Type: AFK
User stories: (post-PRD workspace UX — complete conversation display with bounded AI context)

## What to build

Separate the complete Session History read model used by the chat from the recent-history window supplied to the AI. Opening a Repository Session displays its newest messages and supports loading older pages upward until the complete persisted conversation is visible in chronological order. The initial page contains the latest 50 messages and preserves the user’s scroll position as older pages are prepended.

Question reformulation and task planning continue to receive a bounded context, now canonically the ten most recent Session History messages. Align the PRD, backend plan, configuration, and tests with the glossary’s ten-message rule; full UI history must never be supplied to the AI merely because it was loaded for display.

## Acceptance criteria

- [ ] The owned Session History API supports deterministic pagination over the complete persisted history and returns enough pagination information to request older messages.
- [ ] Opening a Repository Session fetches its latest 50 messages, renders them chronologically, and starts at the newest message.
- [ ] Scrolling upward loads and prepends older pages without duplicates, gaps, reversed messages, or a disruptive scroll jump.
- [ ] Pagination continues until the complete persisted Session History is available to the user.
- [ ] Question reformulation and task planning receive at most the ten most recent messages regardless of how much history the UI has loaded.
- [ ] The PRD, backend plan, configuration, glossary, and automated tests consistently state and enforce the ten-message AI-context limit.
- [ ] Ownership rules, empty history, page boundaries, stable ordering, and long-history UI behavior are tested.

## Blocked by

- [Issue 43](43-deep-linked-repository-session-navigation.md)
