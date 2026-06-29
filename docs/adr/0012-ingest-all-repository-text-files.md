# Ingest all repository text files, not only Python

## Status

accepted

Broadens the **Repository Document** and **Code Chunk** glossary terms and refines **Repository** in `CONTEXT.md`. Shares the single ingestion entry point with the file-level Repository Synchronization of ADR [0008](0008-poll-upstream-for-sync-availability-not-auto-sync.md).

## Context and decision

The copilot indexed only `.py` files, so it had no view of how a project is built or configured — `pyproject.toml`, CI workflows, `Dockerfile`, `Makefile`, requirements, and documentation were invisible to retrieval, even though that context materially helps both repository questions and test generation. We decided to index **every committed UTF-8 text file**, not only Python, while keeping the product anchored to Python.

- **Blocklist, not allowlist.** We index all text files and exclude a small set, rather than curating an allowlist of extensions. An allowlist silently drops the unanticipated build/config file that is exactly the point of this change.
- **GitLoader already does most of the filtering for free.** `repo.tree().traverse()` sees only committed/tracked files; `repo.ignored(...)` skips git-ignored paths (caches, `.venv/`, `htmlcov/`, `__pycache__/`); and the UTF-8 decode guard skips binaries. So no binary-content sniff and no gitignore handling is needed in our code.
- **Two guards GitLoader lacks: size cap and a lock/vendor denylist.** A committed, non-ignored, large text file (lock files, vendored or minified assets, big data files) would otherwise load. The `file_filter` rejects files over a configurable byte cap (`MAX_INGEST_FILE_BYTES`, default 1 MB) and a small denylist of lock files (`poetry.lock`, `package-lock.json`, `yarn.lock`, `*.lock`) and committed vendor directories.
- **Per-language chunking with a generic fallback.** The single Python-aware splitter becomes a per-language router: `.py` keeps `Language.PYTHON` separators, recognized source/markup extensions (`.md`, JS/TS, HTML, …) use their `RecursiveCharacterTextSplitter.from_language` separators, and everything else falls back to a plain recursive splitter. `_split` groups documents by resolved language and splits each group with its splitter.
- **Still require at least one Python file.** The product generates Python tests, so a repo with zero `.py` files cannot do its core job. Ingestion still fails with "Repository has no Python files" when no Python document is present; non-Python files are supporting context only. Each document is stamped with a derived `category` (code/config/docs/other) and `language`.

## Considered options

- **Blocklist + guards vs. curated allowlist vs. literally everything** — chose blocklist + guards. Allowlist defeats the goal (it omits the surprising config file); "literally everything" pollutes the index and risks non-text content, which GitLoader's decode guard already prevents anyway.
- **Per-language routing vs. one generic splitter vs. Python-only-aware** — chose per-language routing. A single generic splitter would degrade the code-retrieval quality the RAG relies on; keeping only Python-aware splitting handles `.py` well but chunks Markdown/YAML crudely.
- **Require ≥1 Python file vs. accept any text file** — chose to keep the Python requirement, preserving the "Repository = Python codebase" invariant; a YAML-only repo would index but could never generate tests.

## Consequences

- **Larger index, higher embedding spend, more retrieval candidates.** More documents and chunks per repository increase Voyage/Cohere usage and add non-code candidates to the retrieval pool; the reranker and parent-hydration de-duplication absorb the noise, and category metadata leaves the door open to bias retrieval later.
- **Repository Synchronization broadens automatically.** Because ingestion is the shared entry point (ADR 0008's file-level sync calls the same path), syncs now add, replace, and remove config/docs files too — a consistent, benign extension of the same mechanism.
- **`category`/`language` live in relational `doc_metadata` and ride along on chunk metadata.** No Weaviate schema change is required now; chunk-level filtering on category would need a property added later.
