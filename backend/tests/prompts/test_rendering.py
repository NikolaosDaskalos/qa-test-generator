"""The shared context renderers: source-labeled documents and proposed file blocks.

These pin the display rules for how Code Chunk source labels and proposed Test
File contents appear in an LLM prompt, directly and without any model loop.
"""

from app.models import RepositoryDocument
from app.prompts.rendering import format_files, format_repository_documents
from app.schemas import GeneratedFile


def _source(source: str, content: str) -> RepositoryDocument:
    return RepositoryDocument(content=content, doc_metadata={"source": source})


def test_format_repository_documents_labels_a_document_with_its_source() -> None:
    """A single document renders as a [Source: <path>] label above its content."""
    rendered = format_repository_documents([_source("app/auth.py", "def login(): ...")])

    assert rendered == "[Source: app/auth.py]\ndef login(): ..."


def test_format_repository_documents_separates_documents_in_order() -> None:
    """Multiple documents render in order, joined by a blank-line ``---`` separator."""
    rendered = format_repository_documents([_source("app/auth.py", "def login(): ..."), _source("app/users.py", "def create(): ...")])

    assert rendered == "[Source: app/auth.py]\ndef login(): ...\n\n---\n\n[Source: app/users.py]\ndef create(): ..."


def test_format_repository_documents_falls_back_to_a_question_mark_when_source_is_missing() -> None:
    """A document with no ``source`` metadata is labeled ``[Source: ?]`` rather than erroring."""
    document = RepositoryDocument(content="orphan chunk", doc_metadata={})

    rendered = format_repository_documents([document])

    assert rendered == "[Source: ?]\norphan chunk"


def test_format_repository_documents_renders_an_empty_list_as_an_empty_string() -> None:
    """No documents renders as the empty string so the caller can omit the section."""
    assert format_repository_documents([]) == ""


def test_format_files_labels_a_file_with_its_path() -> None:
    """A single proposed file renders as a [File: <path>] block above its full contents."""
    rendered = format_files([GeneratedFile(path="tests/test_auth.py", content="def test_login(): ...")])

    assert rendered == "[File: tests/test_auth.py]\ndef test_login(): ..."


def test_format_files_separates_files_in_order() -> None:
    """Multiple files render in order, joined by the same blank-line ``---`` separator."""
    rendered = format_files(
        [GeneratedFile(path="tests/test_auth.py", content="def test_login(): ..."), GeneratedFile(path="tests/test_users.py", content="def test_create(): ...")]
    )

    assert rendered == "[File: tests/test_auth.py]\ndef test_login(): ...\n\n---\n\n[File: tests/test_users.py]\ndef test_create(): ..."


def test_format_files_renders_an_empty_list_as_an_empty_string() -> None:
    """No proposed files renders as the empty string so the caller can omit the section."""
    assert format_files([]) == ""
