# Ingest all committed repository text files, not just Python

Status: ready-for-agent
Type: AFK
User stories: (new — richer build/configuration/structure context for repository questions and test generation)

## What to build

Broaden Repository ingestion so the index contains **every committed UTF-8 text file**, not only `.py` — `pyproject.toml`, CI workflows, `Dockerfile`, `Makefile`, requirements, and documentation become visible to retrieval and the code generator. Per ADR [0012](../adr/0012-ingest-all-repository-text-files.md), this is a blocklist, not an allowlist: index everything text-based and exclude a small set.

The loader (`GitLoader`) already does most of the filtering for free — it walks only the committed tree, skips git-ignored paths (caches, `.venv/`, `htmlcov/`, `__pycache__/`), and skips files that fail UTF-8 decode (binaries). The two guards it lacks live in our `file_filter`: reject files over a configurable byte cap (`MAX_INGEST_FILE_BYTES`, default 1 MB, checked via `os.path.getsize`) and a small denylist of lock files (`poetry.lock`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `*.lock`) and committed vendor directories (`vendor/`, `third_party/`, `node_modules/`).

The Repository stays anchored to Python: ingestion still fails with "Repository has no Python files" when no `.py` document is present (`ingestor.py` guard retained), and non-Python files are supporting context only. Non-Python files are split with a plain generic recursive splitter in this slice (language-aware splitting is issue 56). Because ingestion is the shared entry point, Repository Synchronization broadens to add/replace/remove these files too — a consistent extension of the same mechanism.

## Acceptance criteria

- [ ] The ingestion `file_filter` accepts all committed files by default, no longer restricting to `.py`.
- [ ] A configurable `MAX_INGEST_FILE_BYTES` setting (default 1_000_000) excludes any file larger than the cap, checked before the file is read.
- [ ] A denylist excludes lock files (`poetry.lock`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `*.lock`) and committed vendor directories (`vendor/`, `third_party/`, `node_modules/`).
- [ ] Binary files and git-ignored files are still excluded (relying on GitLoader's decode and `repo.ignored` handling — no separate binary sniff added).
- [ ] Ingestion still fails with "Repository has no Python files" when the repository contains zero `.py` files; a repository with `.py` files plus other text files indexes successfully.
- [ ] Non-Python files are chunked and persisted as Repository Documents and Code Chunks alongside Python files, scoped to the correct Repository and tenant.
- [ ] Retrieval can surface non-Python files (e.g. a question about how the project is built returns `pyproject.toml`/`Dockerfile`/CI content).
- [ ] Repository Synchronization re-runs through the same path and correctly adds, replaces, and removes non-Python files.
- [ ] Tests cover: a repo with mixed file types indexes all of them; a repo with no `.py` files fails the Python guard; an oversized file is skipped; a `*.lock`/vendor file is skipped; a binary/git-ignored file never appears.

## Notes / limits

- This slice uses a single generic splitter for non-Python files; per-language splitting and file-type metadata are issue [56](56-language-aware-chunking-and-file-type-metadata.md).
- Larger index means higher embedding/rerank spend and more (non-code) retrieval candidates; the reranker and parent de-duplication absorb the noise. Category-based retrieval biasing is deferred (issue 56 lays the metadata groundwork).

## Related

- Realizes ADR [0012](../adr/0012-ingest-all-repository-text-files.md).
- Shares the ingestion entry point with the file-level Repository Synchronization of ADR [0008](../adr/0008-poll-upstream-for-sync-availability-not-auto-sync.md).
