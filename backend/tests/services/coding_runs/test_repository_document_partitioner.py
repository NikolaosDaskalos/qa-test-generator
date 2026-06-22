"""Specify Repository Document partitioning for Code Generation Tasks."""

import uuid

import pytest

from app.db.models import RepositoryDocument
from app.schemas import RetrievalRequest
from app.services.coding_runs.repository_document_partitioner import RepositoryDocumentPartitioner, RepositoryDocumentPartitionRequest


class _Retriever:
    def __init__(self, documents_by_query) -> None:
        self.documents_by_query = documents_by_query

    def retrieve_documents(self, query, **_options):
        return self.documents_by_query.get(query, [])


def test_partition_routes_source_and_test_documents_and_confines_path_hints(tmp_path) -> None:
    repository_id = uuid.uuid4()
    source_code_document = RepositoryDocument(repository_id=repository_id, content="implementation", doc_metadata={"source": "app/auth.py"})
    test_document = RepositoryDocument(repository_id=repository_id, content="tests", doc_metadata={"source": "tests/test_auth.py"})
    partitioner = RepositoryDocumentPartitioner(_Retriever({"auth implementation": [source_code_document], "auth tests": [test_document]}))

    partition = partitioner.partition(
        RepositoryDocumentPartitionRequest(
            retrieval_requests=[
                RetrievalRequest(document_type="source", description="auth implementation", candidate_paths=["app/auth.py", "/etc/passwd"]),
                RetrievalRequest(document_type="test", description="auth tests", candidate_paths=["tests/test_auth.py", "../escape"]),
            ],
            repository_id=repository_id,
            checkout_root=tmp_path,
        )
    )

    assert partition.source_documents == [source_code_document]
    assert partition.test_documents == [test_document]
    assert partition.candidate_hints == ["app/auth.py", "tests/test_auth.py"]


def test_partition_de_duplicates_safe_hints_in_first_seen_order(tmp_path) -> None:
    """Safe candidate hints repeated across requests survive once, in first-seen order."""
    repository_id = uuid.uuid4()
    partitioner = RepositoryDocumentPartitioner(_Retriever({}))

    partition = partitioner.partition(
        RepositoryDocumentPartitionRequest(
            retrieval_requests=[
                RetrievalRequest(document_type="source", description="auth", candidate_paths=["app/auth.py", "app/db.py"]),
                RetrievalRequest(document_type="test", description="auth tests", candidate_paths=["app/db.py", "tests/test_auth.py", "app/auth.py"]),
            ],
            repository_id=repository_id,
            checkout_root=tmp_path,
        )
    )

    assert partition.candidate_hints == ["app/auth.py", "app/db.py", "tests/test_auth.py"]


def test_partition_without_a_checkout_root_fails_instead_of_dropping_candidate_hints() -> None:
    """A Code Generation partition cannot proceed without a checkout to confine hints against."""
    partitioner = RepositoryDocumentPartitioner(_Retriever({}))
    request = RepositoryDocumentPartitionRequest(
        retrieval_requests=[RetrievalRequest(document_type="source", description="auth", candidate_paths=["app/auth.py"])],
        repository_id=uuid.uuid4(),
        checkout_root=None,
    )

    with pytest.raises(ValueError):
        partitioner.partition(request)
