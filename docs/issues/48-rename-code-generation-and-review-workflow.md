# Rename the code-generation and review workflow

Status: completed
Type: AFK
User stories: 30-55, 67-72, 102-103

## What to build

Apply the canonical Code Generation Task, Code Generator, Code Reviewer, Patch Review, and Generation Retries language through the complete generation workflow. This is strictly a terminology and identifier refactor: Code Generation Tasks may still change Test Files only, and every existing validation, review, escalation, approval, rejection, and cleanup rule remains intact.

Use general code-generation names for the workflow and agent roles while retaining Test File and Test Patch where those terms identify the deliberately test-only output.

## Acceptance criteria

- [x] The inferred request intent and graph branch use code-generation terminology instead of test-generation terminology across backend and frontend contracts.
- [x] The code generator and `CodeReviewer` replace test-generator and patch-reviewer class, dependency, prompt, fake, and test names.
- [x] Patch Review remains the canonical scored assessment produced by the Code Reviewer.
- [x] Generation Retries replace Revision Budget and Review Retry terminology in configuration, state, policy modules, functions, events, documentation strings, and tests.
- [x] The configured retry default, score threshold, hard Test File restriction, escalation behavior, and human decision flow do not change.
- [x] Agent Stream payload behavior and persisted Coding Run compatibility remain unchanged except for internal or descriptive terminology.
- [x] Generated frontend contracts, UI copy, backend tests, and frontend tests use the canonical names.

## Blocked by

- [Issue 47](47-rename-rag-language-to-repository-documents.md)
