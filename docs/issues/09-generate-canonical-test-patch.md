# Generate canonical diffs for existing Test Files

Status: completed
Type: AFK
User stories: 38-40, 42-45, 54

## What to build

Extend the Coding Run through generation for existing Test Files. Restore the shared checkout to the
indexed default-branch commit, create a unique non-default temporary branch, ask the generator for
structured complete-file proposals, validate them, write them, and derive the canonical unified diff
with Git.

The generator is a bounded ReAct node whose **only** tool is `web_search` (Tavily), used to look up a
test framework's current syntax and best practices. It has no shell or filesystem tools. The loop is
bounded by single-tool binding and a graph recursion cap. Web results are `External Reference`s, kept
separate from Repository Evidence (`source_evidence` / `test_evidence`) and never used to ground
claims about the Repository's code — only how tests are written. Web search is reachable only on this
test-generation path.

The LLM must not author or apply an arbitrary unified diff, and proposals must not modify application
code.

## Acceptance criteria

- [x] Generation starts from a clean checkout restored to the Repository's indexed commit on a
      uniquely named non-default temporary branch.
- [x] The generator receives the Test-Generation Task, validated Repository Evidence (source and
      test), and may call only the bounded `web_search` tool — no shell or filesystem tools.
- [x] The `web_search` loop is bounded; `researching` stage progress is streamed when the tool runs,
      and External References are collected separately from Repository Evidence.
- [x] Generator output is a structured collection of complete file paths and complete contents
      rather than diff text.
- [x] Existing recognized Python Test Files may be modified.
- [x] Absolute paths, traversal outside the checkout, symlink targets, non-Python files, and
      application or source files are rejected before writing.
- [x] The backend writes only validated Test Files and obtains the displayed Test Patch from Git.
- [x] The Coding Run persists generated file proposals, collected External References, and the
      canonical diff; the stream emits `generating`/patch progress and a terminal `PatchResult`
      (coding_run_id, diff, generated_files, external_references), or `RunFailure` on generation or
      validation failure.
- [x] Tests cover clean branch preparation, structured generation, the bounded web_search loop
      (including that a repository-question never reaches the web), External Reference separation,
      each rejection boundary, canonical diff generation, and generation or validation Run Failure.

## Blocked by

- [08 - Route Request Intent and plan Test-Generation Tasks from Repository Evidence](08-plan-test-generation-from-evidence.md)

## Design

See [ADR 0002 - Intent-routed unified LangGraph for repository sessions](../adr/0002-intent-routed-unified-langgraph.md).
