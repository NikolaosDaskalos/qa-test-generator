# Navigate nested Repository Sessions with durable URLs

Status: ready-for-agent
Type: AFK
User stories: 18-20, 85-94, 105

## What to build

Turn the left panel’s main area into an AI-chat-style Repository tree. Each Repository is a collapsible group; only the active Repository is expanded, and its existing Repository Sessions plus a “New session” action appear beneath it. Selecting a Repository must never create a Repository Session automatically.

Each selected Repository Session has a durable URL containing both its Repository and Repository Session identifiers. On login or workspace reload, reopen the most recently used accessible Repository Session. When switching Repositories, reopen that Repository’s last-used session when one was previously selected; otherwise expand the group without selecting or creating a session. A ready Repository with no selected session shows a central “Start a new session” state.

## Acceptance criteria

- [ ] The sidebar lists Repositories as collapsible groups and keeps only the active Repository expanded.
- [ ] An expanded ready Repository lists its existing Repository Sessions and a “New session” action beneath it.
- [ ] Selecting or expanding a Repository never creates a Repository Session implicitly.
- [ ] “New session” explicitly creates a blank Repository Session, selects it, and navigates to its durable Repository/Repository Session URL.
- [ ] Selecting an existing Repository Session loads its chat workspace and updates the URL.
- [ ] A direct session URL, browser refresh, and browser back/forward navigation restore the correct accessible Repository and Repository Session.
- [ ] Login and root-workspace navigation reopen the last-used accessible Repository Session; stale or inaccessible saved selections fall back safely.
- [ ] Switching Repositories restores that Repository’s last-used session when available, otherwise no session is selected.
- [ ] Ready Repositories without a selected session show a central “Start a new session” state; non-ready Repositories continue to show their status view.
- [ ] Desktop, collapsed-sidebar, and mobile-drawer navigation behavior is covered by frontend tests.

## Blocked by

- [Issue 41](41-copilot-repository-empty-state.md)
