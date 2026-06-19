# Separate Coding Run logic from AI agents

Status: ready-for-agent
Type: AFK
User stories: 30-72, 102-103

## What to build

Create a cohesive Coding Run feature for deterministic lifecycle behavior while retaining LangChain and LangGraph implementation in a distinct `agents` package. Coding Run patch construction, Test File validation, Generation Retries, recording, workspace management, Patch Review policy, decisions, and publishing belong to the Coding Run feature. Agent definitions, graph construction, nodes, prompts, middleware, and AI tools belong to `agents`.

Keep `rag` as its own explicit package. Preserve the accepted unified LangGraph, the single Code Generator, the Code Reviewer, scored Patch Review, human escalation, and all Agent Stream behavior.

## Acceptance criteria

- [ ] Deterministic Coding Run rules and workflows have one predictable `coding_runs` home and do not import FastAPI, LangChain, or LangGraph.
- [ ] LangChain and LangGraph code lives under a separate plural `agents` package, including graph nodes, Code Generator, Code Reviewer, prompts, middleware, and AI tools.
- [ ] RAG remains a separate `rag` package and is not folded into agents or renamed to evidence.
- [ ] Graph nodes adapt graph state to Coding Run interfaces instead of owning patch, retry, validation, recording, workspace, or decision rules.
- [ ] The unified graph and its repository-question and code-generation branches retain their current routing, streaming, checkpoint, and resume behavior.
- [ ] Patch validation, review scoring, Generation Retries, approval, rejection, Git cleanup, and persisted outcomes remain unchanged.
- [ ] Coding Run behavior can be tested through its interfaces without compiling a graph, while graph integration tests cover adapter wiring.

## Blocked by

- [Issue 47](47-rename-rag-language-to-repository-documents.md)
- [Issue 48](48-rename-code-generation-and-review-workflow.md)
- [Issue 50](50-reorganize-repository-sessions.md)
