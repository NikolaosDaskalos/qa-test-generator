"""Test tenant-aware document ingestion and deletion behavior."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from git import Repo
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from app.core import settings
from app.core.errors.rag_errors import IngestorError
from app.integrations.weaviate import WeaviateResources
from app.rag import DocumentIngestor
from app.rag.ingestor import _file_type_for


def _make_git_repo(root: Path, tracked: dict[str, bytes | str], *, ignored: dict[str, bytes | str] | None = None) -> tuple[Path, str]:
    """Create a committed Git repository and return its path and active branch name."""
    repo = Repo.init(root)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test")
        config.set_value("user", "email", "test@example.com")

    for relative_path, content in tracked.items():
        file_path = root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        repo.index.add([str(file_path)])
    repo.index.commit("initial commit")

    for relative_path, content in (ignored or {}).items():
        file_path = root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    return root, repo.active_branch.name


def _loader_ingestor() -> DocumentIngestor:
    """Build an ingestor for exercising the real load path without persistence."""
    return DocumentIngestor(_resources(), FakeRepositoryDocumentStore())


class FakeTenants:
    """Maintain an in-memory set of Weaviate tenant names."""

    def __init__(self) -> None:
        """Initialize an empty tenant registry."""
        self.names: set[str] = set()

    def get_by_names(self, names):
        """Return known tenants matching the requested names."""
        return {name: object() for name in names if name in self.names}

    def create(self, tenants):
        """Add tenant objects to the registry."""
        self.names.update(tenant.name for tenant in tenants)


class FakeTenantCollection:
    """Record tenant-scoped deletion filters."""

    def __init__(self) -> None:
        """Initialize deletion tracking."""
        self.deleted_filters = []
        self.data = SimpleNamespace(delete_many=self.delete_many)

    def delete_many(self, *, where):
        """Record a bulk-deletion filter."""
        self.deleted_filters.append(where)


class FakeCollection:
    """Provide tenant management and tenant-scoped collections."""

    def __init__(self) -> None:
        """Initialize tenant registries and collection storage."""
        self.tenants = FakeTenants()
        self.tenant_collections = {}

    def with_tenant(self, tenant):
        """Return or create a fake collection for a tenant."""
        return self.tenant_collections.setdefault(tenant, FakeTenantCollection())


class FakeCollections:
    """Expose one collection through the client registry API."""

    def __init__(self, collection) -> None:
        """Store the collection returned by lookups."""
        self.collection = collection

    def get(self, name):
        """Return the configured collection after checking its name."""
        assert name == settings.WEAVIATE_COLLECTION
        return self.collection


class FakeClient:
    """Provide a minimal Weaviate client for ingestion tests."""

    def __init__(self, collection) -> None:
        """Initialize the client with one fake collection."""
        self.collections = FakeCollections(collection)


class FakeVectorStore:
    """Record vector-store additions and deletions."""

    def __init__(self) -> None:
        """Initialize call tracking."""
        self.add_calls = []
        self.delete_calls = []

    def add_documents(self, documents, **kwargs):
        """Record documents and return their supplied IDs."""
        self.add_calls.append((documents, kwargs))
        return kwargs["ids"]

    def delete(self, **kwargs):
        """Record a vector-store deletion call."""
        self.delete_calls.append(kwargs)


class FakeRepositoryDocumentStore:
    """Record source-document replacement and cleanup."""

    def __init__(self) -> None:
        self.replace_calls = []
        self.delete_calls = []

    def replace_for_repository(self, repository_id, repository_documents):
        self.replace_calls.append((repository_id, repository_documents))
        return repository_documents

    def delete_by_repository(self, repository_id):
        self.delete_calls.append(repository_id)


def _resources() -> WeaviateResources:
    """Build shared resources from ingestion test doubles."""
    return WeaviateResources(client=FakeClient(FakeCollection()), vector_store=FakeVectorStore())


def _bare_ingestor(documents, resources):
    """Build an ingestor without loading the real tokenizer."""
    ingestor = DocumentIngestor(resources, FakeRepositoryDocumentStore())
    ingestor._load = lambda *args: documents
    ingestor._split = lambda *args: documents
    return ingestor


def test_ingestion_replaces_repository_chunks_with_deterministic_ids() -> None:
    """Replace existing chunks while preserving deterministic IDs."""
    repository_id = uuid.uuid4()
    user_id = uuid.uuid4()
    commit_sha = "a" * 40
    resources = _resources()
    documents = [Document(page_content="print('one')", metadata={"source": "one.py"}), Document(page_content="print('two')", metadata={"source": "two.py"})]
    ingestor = _bare_ingestor(documents, resources)

    first_count = ingestor.ingest(Path("/repo"), repository_id, "main", commit_sha, user_id)
    first_ids = resources.vector_store.add_calls[0][1]["ids"]
    second_count = ingestor.ingest(Path("/repo"), repository_id, "main", commit_sha, user_id)

    assert first_count == second_count == 2
    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    assert collection.tenants.names == {str(user_id)}
    assert resources.vector_store.add_calls[1][1]["ids"] == first_ids
    assert resources.vector_store.add_calls[0][1]["tenant"] == str(user_id)
    assert len(collection.with_tenant(str(user_id)).deleted_filters) == 2


def test_ingestion_stores_repository_snapshot_metadata_and_ids() -> None:
    """Identify every Code Chunk by Repository, commit SHA, and source path."""
    repository_id = uuid.uuid4()
    user_id = uuid.uuid4()
    resources = _resources()
    documents = [Document(page_content="print('one')", metadata={"source": "one.py"})]
    ingestor = _bare_ingestor(documents, resources)

    ingestor.ingest(Path("/repo"), repository_id, "main", "a" * 40, user_id)
    first_documents, first_options = resources.vector_store.add_calls[0]
    first_metadata = dict(first_documents[0].metadata)
    ingestor.ingest(Path("/repo"), repository_id, "main", "b" * 40, user_id)
    second_documents, second_options = resources.vector_store.add_calls[1]
    second_metadata = dict(second_documents[0].metadata)
    ingestor.ingest(Path("/repo"), uuid.uuid4(), "main", "a" * 40, user_id)
    third_options = resources.vector_store.add_calls[2][1]

    assert first_metadata == {
        "source": "one.py",
        "repository_id": str(repository_id),
        "commit_sha": "a" * 40,
        "parent_id": str(uuid.uuid5(repository_id, f"{'a' * 40}:one.py")),
    }
    assert second_metadata["commit_sha"] == "b" * 40
    assert first_options["ids"] != second_options["ids"]
    assert first_options["ids"] != third_options["ids"]


def test_empty_ingestion_is_rejected_without_writes() -> None:
    """Reject repositories that contain no usable Python documents."""
    resources = _resources()
    ingestor = _bare_ingestor([], resources)

    with pytest.raises(IngestorError, match="no Python files"):
        ingestor.ingest(Path("/repo"), uuid.uuid4(), "main", "a" * 40, uuid.uuid4())

    assert resources.vector_store.add_calls == []
    assert ingestor.repository_document_store.replace_calls == []


def test_ingestion_requires_at_least_one_python_file() -> None:
    """Reject a repository whose only loaded documents are non-Python text files."""
    resources = _resources()
    documents = [
        Document(page_content="[project]", metadata={"source": "pyproject.toml"}),
        Document(page_content="# Demo", metadata={"source": "README.md"}),
    ]
    ingestor = _bare_ingestor(documents, resources)

    with pytest.raises(IngestorError, match="no Python files"):
        ingestor.ingest(Path("/repo"), uuid.uuid4(), "main", "a" * 40, uuid.uuid4())

    assert resources.vector_store.add_calls == []
    assert ingestor.repository_document_store.replace_calls == []


def test_repository_deletion_is_idempotent_when_tenant_is_missing() -> None:
    """Do not create a tenant solely to delete absent repository chunks."""
    resources = _resources()
    ingestor = DocumentIngestor(resources, FakeRepositoryDocumentStore())
    user_id = uuid.uuid4()

    ingestor.delete_repository(uuid.uuid4(), user_id=user_id)

    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    assert collection.tenants.names == set()
    assert collection.tenant_collections == {}


def test_repository_deletion_uses_existing_user_tenant() -> None:
    """Delete repository chunks only within the owner's existing tenant."""
    resources = _resources()
    ingestor = DocumentIngestor(resources, FakeRepositoryDocumentStore())
    user_id = uuid.uuid4()
    collection = resources.client.collections.get(settings.WEAVIATE_COLLECTION)
    collection.tenants.names.add(str(user_id))

    ingestor.delete_repository(uuid.uuid4(), user_id=user_id)

    assert len(collection.with_tenant(str(user_id)).deleted_filters) == 1


def test_ingestion_uses_shared_resources_when_write_fails() -> None:
    """Keep the shared resource instance when a write propagates failure."""
    resources = _resources()
    ingestor = _bare_ingestor([Document(page_content="content", metadata={"source": "file.py"})], resources)
    resources.vector_store.add_documents = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("write failed"))

    with pytest.raises(RuntimeError, match="write failed"):
        repository_id = uuid.uuid4()
        ingestor.ingest(Path("/repo"), repository_id, "main", "a" * 40, uuid.uuid4())

    assert ingestor.resources is resources
    assert ingestor.repository_document_store.delete_calls == [repository_id]


def test_split_groups_documents_by_resolved_language() -> None:
    """Group documents by resolved language, splitting Markdown with Markdown separators and `.py` with Python."""
    ingestor = _loader_ingestor()
    routed: list[Language | None] = []
    used: dict[Language | None, RecursiveCharacterTextSplitter] = {}
    real_splitter_for = ingestor._splitter_for

    def recording_splitter_for(language):
        routed.append(language)
        splitter = real_splitter_for(language)
        used[language] = splitter
        return splitter

    ingestor._splitter_for = recording_splitter_for
    documents = [
        Document(page_content="def f():\n    return 1", metadata={"source": "app.py"}),
        Document(page_content="# Title\n\nbody", metadata={"source": "README.md"}),
        Document(page_content="x = 1", metadata={"source": "other.py"}),
    ]

    chunks = ingestor._split(documents)

    assert routed.count(Language.PYTHON) == 1  # two `.py` files share one grouped split call
    assert sorted(routed, key=str) == sorted([Language.PYTHON, Language.MARKDOWN], key=str)
    assert used[Language.MARKDOWN]._separators == RecursiveCharacterTextSplitter.get_separators_for_language(Language.MARKDOWN)
    assert used[Language.PYTHON]._separators == RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON)
    assert {chunk.metadata["source"] for chunk in chunks} == {"app.py", "README.md", "other.py"}


def test_file_type_resolution_maps_extensions_and_falls_back() -> None:
    """Resolve each file to a chunking language and category, defaulting unmapped files to generic/other."""
    python = _file_type_for("app.py")
    markdown = _file_type_for("docs/README.md")
    config = _file_type_for("pyproject.toml")
    other = _file_type_for("data.bin")

    assert (python.language, python.category) == (Language.PYTHON, "code")
    assert (markdown.language, markdown.category) == (Language.MARKDOWN, "docs")
    assert (config.language, config.category) == (None, "config")
    assert (other.language, other.category) == (None, "other")


def test_splitter_cache_builds_one_splitter_per_language() -> None:
    """Construct each language's splitter once and reuse it, with language-specific separators."""
    ingestor = _loader_ingestor()

    python_first = ingestor._splitter_for(Language.PYTHON)
    python_second = ingestor._splitter_for(Language.PYTHON)
    generic = ingestor._splitter_for(None)

    assert python_first is python_second
    assert generic is not python_first
    assert python_first._separators == RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON)
    assert generic._separators == ["\n\n", "\n", " ", ""]


def test_load_ingests_every_committed_text_file(tmp_path: Path) -> None:
    """Load all committed UTF-8 text files, not only Python sources."""
    repo_path, branch = _make_git_repo(
        tmp_path,
        {
            "app.py": "print('hi')",
            "pyproject.toml": "[project]\nname = 'demo'",
            "Dockerfile": "FROM python:3.13",
            "docs/README.md": "# Demo",
        },
    )
    ingestor = _loader_ingestor()

    sources = {doc.metadata["source"] for doc in ingestor._load(repo_path, branch)}

    assert sources == {"app.py", "pyproject.toml", "Dockerfile", "docs/README.md"}


def test_load_stamps_category_and_language_on_each_document(tmp_path: Path) -> None:
    """Stamp a derived category and chunking language onto each loaded document's metadata."""
    repo_path, branch = _make_git_repo(
        tmp_path,
        {
            "app.py": "x = 1",
            "pyproject.toml": "[project]",
            "docs/guide.md": "# Guide",
            "data.csv": "a,b\n1,2",
        },
    )
    ingestor = _loader_ingestor()

    metadata_by_source = {doc.metadata["source"]: doc.metadata for doc in ingestor._load(repo_path, branch)}

    assert (metadata_by_source["app.py"]["category"], metadata_by_source["app.py"]["language"]) == ("code", "python")
    assert (metadata_by_source["pyproject.toml"]["category"], metadata_by_source["pyproject.toml"]["language"]) == ("config", "text")
    assert (metadata_by_source["docs/guide.md"]["category"], metadata_by_source["docs/guide.md"]["language"]) == ("docs", "markdown")
    assert (metadata_by_source["data.csv"]["category"], metadata_by_source["data.csv"]["language"]) == ("other", "text")


def test_chunk_metadata_carries_category_and_language(tmp_path: Path) -> None:
    """Stamped category and language ride from a loaded document onto each of its chunks."""
    repo_path, branch = _make_git_repo(tmp_path, {"app.py": "x = 1", "docs/guide.md": "# Guide\n\nbody"})
    ingestor = _loader_ingestor()

    chunks = ingestor._split(ingestor._load(repo_path, branch))

    by_source = {chunk.metadata["source"]: chunk.metadata for chunk in chunks}
    assert (by_source["app.py"]["category"], by_source["app.py"]["language"]) == ("code", "python")
    assert (by_source["docs/guide.md"]["category"], by_source["docs/guide.md"]["language"]) == ("docs", "markdown")


def test_load_skips_files_over_the_byte_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip any committed file larger than MAX_INGEST_FILE_BYTES before reading it."""
    monkeypatch.setattr(settings, "MAX_INGEST_FILE_BYTES", 64)
    repo_path, branch = _make_git_repo(
        tmp_path,
        {
            "small.py": "x = 1",
            "huge.py": "# " + "y" * 200,
        },
    )
    ingestor = _loader_ingestor()

    sources = {doc.metadata["source"] for doc in ingestor._load(repo_path, branch)}

    assert sources == {"small.py"}


def test_load_skips_lock_files_and_vendor_directories(tmp_path: Path) -> None:
    """Skip lock files and committed vendor directories via the denylist."""
    repo_path, branch = _make_git_repo(
        tmp_path,
        {
            "app.py": "keep = True",
            "poetry.lock": "[[package]]",
            "package-lock.json": "{}",
            "Cargo.lock": "[[package]]",
            "assets.min.lock": "blob",
            "vendor/lib.py": "vendored = 1",
            "third_party/helper.py": "vendored = 2",
            "node_modules/pkg/index.js": "module.exports = {}",
        },
    )
    ingestor = _loader_ingestor()

    sources = {doc.metadata["source"] for doc in ingestor._load(repo_path, branch)}

    assert sources == {"app.py"}


def test_load_skips_binary_and_git_ignored_files(tmp_path: Path) -> None:
    """Never index binary files or git-ignored paths, leaning on GitLoader's guards."""
    repo_path, branch = _make_git_repo(
        tmp_path,
        {
            "app.py": "keep = True",
            "logo.png": b"\x89PNG\r\n\x1a\n\x00\xff\xfe",
            ".gitignore": "secret.py\n",
        },
        ignored={"secret.py": "password = 'x'"},
    )
    ingestor = _loader_ingestor()

    sources = {doc.metadata["source"] for doc in ingestor._load(repo_path, branch)}

    assert sources == {"app.py", ".gitignore"}
