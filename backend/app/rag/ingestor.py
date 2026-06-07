"""Builds vector store at startup of the application.
If the Repo is already indexed skips the execution.
"""
import re
import logging
import uuid
import os
from langchain_community.document_loaders import GitLoader
from langchain_core.documents import Document
import giturlparse
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language, TextSplitter
from transformers import AutoTokenizer, TokenizersBackend
from app.core.config import settings

logger = logging.getLogger(__name__)

# added to remove Hugging Face Warning from AutoTokenizer
os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)


class DocumentIngestor:
    """
    Loads a Git repository, splits Python files into chunks, and stores them in Chroma db.
    """

    def __init__(self, vectorstore):
        self.vectorstore = vectorstore
        self._tokenizer: TokenizersBackend = AutoTokenizer.from_pretrained(
            settings.EMBEDDING_MODEL_TOKENIZER, token=settings.HF_TOKEN)

    def ingest(self, repo_url: str) -> int:
        """
        Full ingestion pipeline: Load -> Split -> Store.
        Skips ingestion when this repo is already in the vector store.
        """
        # TODO same repo names can exists with different users
        if self._is_already_indexed(repo_name):
            logger.info(f"Repository {repo_name} already indexed.")
            return 0

        raw_docs = self._load(repo_name, repo_url)
        if not raw_docs:
            logger.info(f"No files found in {repo_name}")
            return 0

        chunked_docs = self._split(raw_docs)
        self._store(chunked_docs)
        # self._print_debug_documents(raw_docs, chunked_docs)
        return len(chunked_docs)

    def _load(self, repo_name: str, repo_url: str) -> list[Document]:
        """Load Python documents from the Git repository."""

        (settings.REPO_PATH / repo_name).parent.mkdir(parents=True, exist_ok=True)
        # todo add logic for private repos with GH_TOKEN
        git_loader: GitLoader = GitLoader(
            repo_path=str(settings.REPO_PATH / repo_name),
            clone_url=repo_url,
            branch="main",
            file_filter=lambda file_path: str(file_path).endswith(".py"),
        )

        raw_docs: list[Document] = git_loader.load()
        for raw_doc in raw_docs:
            raw_doc.metadata["repo_name"] = repo_name
            raw_doc.metadata["parent_document_id"] = str(uuid.uuid4())
        return raw_docs

    def _split(self, raw_docs: list[Document]) -> list[Document]:
        """Split loaded documents into chunks."""

        splitter: RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            self._tokenizer,
            separators=RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON),
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        return splitter.split_documents(raw_docs)

    def _store(self, chunked_docs: list[Document]) -> None:
        """Store chunks in the provided vector store."""
        self.vectorstore.add_documents(chunked_docs)

    def _is_already_indexed(self, repo_name: str) -> bool:
        """Return True when this repo already exists in the vector store."""
        existing = self.vectorstore._collection.get(
            where={"repo_name": repo_name},
            limit=1,
        )
        return bool(existing["ids"])


    # todo remove this method when app is ready
    def _print_debug_documents(self, raw_docs: list[Document], chunked_docs: list[Document]) -> None:
        """Print raw document and chunk contents for local debugging."""
        for raw_doc in raw_docs:
            print(f"\n/// document ///\n{raw_doc.metadata}\n\n{raw_doc.page_content}\n\n")
            print("-" * 90)
            for chunk in chunked_docs:
                i = 1
                if chunk.metadata["parent_document_id"] == raw_doc.metadata["parent_document_id"]:
                    print(f"\n/// chunk {i}///\n{chunk.metadata}\n\n{chunk.page_content}\n\n")
                    print("-" * 90)
                    i += 1
