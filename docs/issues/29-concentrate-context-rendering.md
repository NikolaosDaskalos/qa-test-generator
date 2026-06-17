# Concentrate the evidence and file-block context renderers

Status: completed
Type: AFK
User stories: (refactor — shared context rendering behind US 06 answering, 08-12 generation/revision/review)

## What to build

The `[Source: …]`-labeled Repository Evidence renderer is duplicated byte-for-byte
across the generator, the reviewer, and the answer path (where it is named
`_format_docs`), and the `[File: …]`-labeled file-block renderer is duplicated
across the generator and the reviewer. These are the display rules for how Code
Chunk source labels and proposed Test File contents appear in an LLM prompt, and
they currently have poor locality: a change to the source-label or file-block
format means editing three or two files in lockstep.

Pull the two leaf renderers into one small shared context-rendering module: a
source-labeled evidence/Code-Chunk renderer and a file-block renderer. The
generator, reviser, reviewer, and answer adapters call them instead of holding
private copies. Per-adapter prompt *assembly* stays where it is — which sections
each prompt includes, their order, their headers, and where the canonical diff
and reviewer findings sit all genuinely differ between generate, revise, review,
and answer, so only the duplicated leaf renderers move; the assembly is not
unified.

The answer path's structured citation extraction (projecting retrieved sources
into de-duplicated `Citation` objects for the wire) is a separate concern from
prompt rendering and is left untouched — only its `_format_docs` prompt renderer
is replaced by the shared evidence renderer.

End to end, behavior is unchanged: every prompt renders Repository Evidence and
proposed files exactly as it does today (same `[Source: …]` / `[File: …]` labels,
same `---` separators), and the answer path still emits the same citations.

## Acceptance criteria

- [x] A shared context-rendering module owns the source-labeled evidence renderer
      and the file-block renderer.
- [x] The generator, reviser, reviewer, and answer adapters call the shared
      renderers; no private copy of the evidence or file-block formatter remains in
      any of them.
- [x] Per-adapter prompt assembly (section choice, order, headers, diff/findings
      placement) is unchanged.
- [x] The answer path's citation extraction (`Citation` projection) is untouched;
      only its `_format_docs` prompt renderer is replaced.
- [x] The shared renderers are unit-tested directly (source-label format, file
      block format, separator/order), without invoking a model loop.
- [x] Rendered prompt output is byte-identical to today; the backend suite passes
      excluding known environmental/pre-existing failures.

## Blocked by

None - can start immediately. Independent of issues 26, 27, 28.
