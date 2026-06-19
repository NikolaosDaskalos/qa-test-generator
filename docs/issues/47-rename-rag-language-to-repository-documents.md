# Rename RAG language to Repository Documents

Status: completed
Type: AFK
User stories: 9-17, 26-31, 35-38, 69, 73, 94

## What to build

Apply the canonical Repository Document and Retrieval Request language throughout the complete RAG path without changing retrieval behavior. Repository Documents remain indexed representations of Repository files, Code Chunks remain their searchable segments, and every retrieval stays scoped to the Repository bound to the Repository Session.

The live implementation must stop using “evidence” and “Research Intent” in filenames, class names, method names, state fields, schemas, prompts, generated contracts, and tests. Distinguish source-code Repository Documents from existing-test Repository Documents using explicit document terminology.

## Acceptance criteria

- [x] `RepositoryDocument` replaces the live `SourceDocument` domain and persistence name, with its store, relationships, migrations, and tests updated without data loss.
- [x] `RetrievalRequest` replaces `ResearchIntent` across planner output, schemas, graph state, retrieval orchestration, prompts, and tests.
- [x] Retrieval interfaces and state use document terminology, including source documents and test documents, without live evidence-named files, classes, or methods.
- [x] RAG still indexes Python files into Code Chunks, reranks candidates, hydrates parent Repository Documents, and returns only documents from the requested Repository.
- [x] Repository Synchronization, citations, insufficient-document behavior, and External Reference separation remain unchanged.
- [x] Backend schemas and generated frontend contracts describe Repository Documents consistently.
- [x] Database migration and automated tests prove that existing Repository Documents remain readable and retrieval behavior is unchanged.

## Blocked by

None - can start immediately
