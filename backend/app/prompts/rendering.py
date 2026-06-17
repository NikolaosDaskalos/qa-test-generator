"""Shared leaf renderers for LLM prompt context.

These own the display rules — source labels and file blocks — for how Code Chunk
Repository Evidence and proposed Test File contents appear in a prompt. Per-adapter
prompt *assembly* (which sections, their order, their headers) stays with each
adapter; only these duplicated leaf renderers live here.
"""


def format_evidence(documents: list) -> str:
    """Render Repository Evidence as ``[Source: <path>]``-labeled, ``---``-separated blocks."""
    return "\n\n---\n\n".join(f"[Source: {document.doc_metadata.get('source', '?')}]\n{document.content}" for document in documents)


def format_files(files: list) -> str:
    """Render proposed Test Files as ``[File: <path>]``-labeled, ``---``-separated blocks."""
    return "\n\n---\n\n".join(f"[File: {file.path}]\n{file.content}" for file in files)
