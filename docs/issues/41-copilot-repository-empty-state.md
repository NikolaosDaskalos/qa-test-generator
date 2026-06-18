# Replace the template landing screen with the Copilot Repository empty state

Status: ready-for-agent
Type: AFK
User stories: (post-PRD workspace UX — Repository onboarding and product shell)

## What to build

Replace the authenticated FastAPI template landing screen with the AI Codebase Copilot workspace shell. Remove the generic Dashboard and Items navigation, FastAPI branding, social links, and template footer while retaining the collapsible left panel, Appearance control, and user profile control.

When the user has no Repositories, show a focused central empty state with an “Add your code repository” action. Open Repository registration as a dedicated screen inside the authenticated shell, with the left panel still visible and a Back/Cancel action. The form accepts a GitHub repository URL, mandatory Repository Credential, and optional numeric token-expiration period in days. Successful submission returns to the workspace with the new Repository selected and its returned processing status visible.

When Repositories already exist, expose a compact add action beside the “Repositories” heading that opens the same registration screen.

## Acceptance criteria

- [ ] The authenticated shell is branded “AI Codebase Copilot” and no longer shows Dashboard, Items, FastAPI template branding, template social links, or the generic footer.
- [ ] Appearance and user profile controls remain at the bottom of the collapsible left panel.
- [ ] A user with no Repositories sees a central “Add your code repository” empty-state action rather than an enabled chat or an inline registration form.
- [ ] Repository registration has its own authenticated route, keeps the left panel visible, and provides Back/Cancel navigation.
- [ ] The registration form requires a GitHub repository URL and Repository Credential; token expiration remains an optional positive number of days.
- [ ] Successful registration returns to the workspace with the newly created Repository selected and its current status visible.
- [ ] A user with existing Repositories can reach the same registration screen from an add action beside the Repositories heading.
- [ ] Empty-state, navigation, validation-error, and successful-registration behavior are covered by frontend tests.

## Blocked by

None - can start immediately.
