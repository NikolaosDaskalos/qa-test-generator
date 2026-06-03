"""Builds vector store at startup of the application.
If the Repo is already indexed skips the execution.
"""
import re
import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import GitLoader
from langchain_core.documents import Document
from langchain_voyageai import VoyageAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from transformers import AutoTokenizer
from app.core.config import settings
from app.rag.manager import VectorManager

logger = logging.getLogger(__name__)

class RepositoryIngestor:
    """
    Loads a Git repository, splits Python files into chunks, and stores them in Chroma db.
    """

    def __init__(self, vectorstore):
        self.vectorstore = vectorstore

    def ingest(self, repo_name: str, repo_url: str) -> None:
        """
        Full ingestion pipeline: Load -> Split -> Store.
        Skips ingestion when this repo is already in the vector store.
        """
        self._validate_repo_name(repo_name)

        if self._is_already_indexed(repo_name):
            return

        raw_docs = self._load(repo_name, repo_url)
        chunked_docs = self._split(raw_docs)
        if not chunked_docs:
            return

        self._store(chunked_docs)
        self._print_debug_documents(raw_docs, chunked_docs)

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
        #TODO: remove [-5:] when finished testing
        raw_docs: list[Document] = git_loader.load()[-5:]
        for raw_doc in raw_docs:
            raw_doc.metadata["repo_name"] = repo_name
            raw_doc.metadata["parent_document_id"] = str(uuid.uuid4())
        return raw_docs

    def _split(self, raw_docs: list[Document]) -> list[Document]:
        """Split loaded documents into chunks."""
        splitter: RecursiveCharacterTextSplitter = (
            RecursiveCharacterTextSplitter
            .from_language(Language.PYTHON, chunk_size=500, chunk_overlap=10)
            .from_huggingface_tokenizer(
                AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL_TOKENIZER))
        )
        return splitter.split_documents(raw_docs)

    def _store(self, chunked_docs: list[Document]) -> None:
        """Store chunks in the provided vector store."""
        VectorManager(self.vectorstore).upsert_embeddings(chunked_docs)

    def _is_already_indexed(self, repo_name: str) -> bool:
        """Return True when this repo already exists in the vector store."""
        existing = self.vectorstore._collection.get(
            where={"repo_name": repo_name},
            limit=1,
        )
        return bool(existing["ids"])

    def _validate_repo_name(self, repo_name: str) -> None:
        """Validates repo name for invalid characters."""
        if not repo_name:
            raise ValueError("Repository name cannot be empty")
        if re.search(r"[^A-Za-z0-9_.-]", repo_name):
            raise ValueError("Repository name contains invalid characters")

    #todo remove this method when app is ready
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


def ingest(vectorstore, repo_name: str, repo_url: str) -> None:
    RepositoryIngestor(vectorstore).ingest(repo_name, repo_url)

# TODO: remove this when testing is finished
if __name__ == "__main__":
    embeddings = VoyageAIEmbeddings(model=settings.EMBEDDING_MODEL, output_dimension=settings.EMBEDDING_DIMENSIONS)
    vectorstore = Chroma(
        collection_name="repositories",
        embedding_function=embeddings,
        persist_directory=str(settings.CHROMA_DB_PATH),
    )
    RepositoryIngestor(vectorstore).ingest('heroes-app', "https://github.com/NikolaosDaskalos/fastapi-heroes-app.git")
