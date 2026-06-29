# Language-aware chunking and file-type metadata for ingested files

Status: ready-for-agent
Type: AFK
User stories: (new — improves chunk quality and adds structured file-type metadata for ingested context)

## What to build

Now that all text files are ingested (issue [55](55-ingest-all-repository-text-files.md)), improve how they are chunked and labeled. A single extension→language map drives two things at once, per ADR [0012](../adr/0012-ingest-all-repository-text-files.md):

1. **Per-language chunking.** Replace the single cached splitter with a per-language splitter router: `.py` keeps `Language.PYTHON` separators, recognized source/markup extensions (`.md`→MARKDOWN, JS/TS, HTML, …) use their `RecursiveCharacterTextSplitter.from_language` separators, and everything else falls back to the plain generic recursive splitter from issue 55. `_split` groups loaded documents by resolved language and splits each group with its splitter, then recombines.
2. **File-type metadata.** Stamp a derived `category` (`code` / `config` / `docs` / `other`) and `language` on each Repository Document's `doc_metadata` and on the chunk metadata that rides into Weaviate. No Weaviate schema change is required now; chunk-level filtering on category can come later.

Splitters are cached per language so each is built once. The same chunk size/overlap and tokenizer-sizing as today apply across languages.

## Acceptance criteria

- [ ] An extension→language map resolves each file to a chunking language, with a generic fallback for unmapped extensions.
- [ ] The single `splitter` cached property is replaced by a per-language splitter cache; each language's splitter is constructed once.
- [ ] `_split` groups documents by resolved language and splits each group with the matching splitter; Python chunking behavior is unchanged from before this slice.
- [ ] Each Repository Document records a derived `category` (`code`/`config`/`docs`/`other`) and `language` in `doc_metadata`.
- [ ] The same `category`/`language` ride on chunk metadata into the vector store without requiring a Weaviate schema migration.
- [ ] Retrieval statistics / citations can read the stamped `category` and `language` (e.g. grouping or display), with no regression to existing citation behavior.
- [ ] Tests cover: extension→language resolution including fallback; a Markdown file is split with Markdown separators while a `.py` file keeps Python separators; `category`/`language` are correctly derived and persisted for code, config, docs, and other files.

## Notes / limits

- This slice does not change which files are ingested (that is issue [55](55-ingest-all-repository-text-files.md)); it only changes how they are split and labeled.
- Category metadata is groundwork for future retrieval biasing (e.g. favoring config files for build questions); the biasing itself is out of scope here.

## Related

- Realizes ADR [0012](../adr/0012-ingest-all-repository-text-files.md).
- Blocked by issue [55](55-ingest-all-repository-text-files.md).
