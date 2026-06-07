import uuid
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_community.document_loaders import GitLoader
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_voyageai import VoyageAIEmbeddings
from pydantic import SecretStr
from transformers import AutoTokenizer

from app.core.config import settings


def build_document_ingestor() -> "DocumentIngestor":
    embeddings = VoyageAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        output_dimension=settings.EMBEDDING_DIMENSIONS,
        api_key=SecretStr(settings.VOYAGE_API_KEY),
    )
    vectorstore = Chroma(
        collection_name="documents",
        embedding_function=embeddings,
        persist_directory=str(settings.CHROMA_DB_PATH),
    )
    return DocumentIngestor(vectorstore)


class DocumentIngestor:
    """Loads an existing local Git clone and stores Python chunks in Chroma."""

    def __init__(self, vectorstore: Any):
        self.vectorstore = vectorstore
        self._tokenizer: Any = AutoTokenizer.from_pretrained(
            settings.EMBEDDING_MODEL_TOKENIZER,
            token=settings.HF_TOKEN,
        )

    def ingest(
        self,
        repo_path: Path,
        repository_id: uuid.UUID,
        branch: str,
    ) -> int:
        raw_docs = self._load(repo_path, repository_id, branch)
        chunked_docs = self._split(raw_docs) if raw_docs else []
        repository_key = str(repository_id)
        self.vectorstore._collection.delete(where={"repository_id": repository_key})
        if not chunked_docs:
            return 0

        ids = [
            str(
                uuid.uuid5(
                    repository_id,
                    f"{doc.metadata['source']}:{index}",
                )
            )
            for index, doc in enumerate(chunked_docs)
        ]
        self.vectorstore.add_documents(chunked_docs, ids=ids)
        return len(chunked_docs)

    def _load(
        self,
        repo_path: Path,
        repository_id: uuid.UUID,
        branch: str,
    ) -> list[Document]:
        loader = GitLoader(
            repo_path=str(repo_path),
            branch=branch,
            file_filter=lambda file_path: str(file_path).endswith(".py"),
        )
        raw_docs: list[Document] = loader.load()
        repository_key = str(repository_id)
        for raw_doc in raw_docs:
            source = raw_doc.metadata["source"]
            raw_doc.metadata["repository_id"] = repository_key
            raw_doc.metadata["parent_document_id"] = str(
                uuid.uuid5(repository_id, source)
            )
        return raw_docs

    def _split(self, raw_docs: list[Document]) -> list[Document]:
        splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            self._tokenizer,
            separators=RecursiveCharacterTextSplitter.get_separators_for_language(
                Language.PYTHON
            ),
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        return splitter.split_documents(raw_docs)
