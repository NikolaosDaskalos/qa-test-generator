"""Provide FastAPI dependencies for database, authentication, and Weaviate."""

import logging
from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import ValidationError
from sqlmodel import Session

from app.agents import build_graph
from app.agents.code_generator import CodeGenerator
from app.agents.code_reviewer import CodeReviewer
from app.core import security, settings
from app.db import engine
from app.db.models import User
from app.db.persistence import CodingRunStore, RepositoryDocumentStore, RepositorySessionStore, RepositoryStore
from app.integrations.llm import create_anthropic_chat_model, create_chat_model, create_reranker
from app.integrations.weaviate import WeaviateResources, get_weaviate_resources
from app.rag import DocumentIngestor, DocumentRetriever
from app.schemas import TokenPayload
from app.services import RepositoryService, RepositorySessionService
from app.services.coding_runs.patch_publisher import build_patch_publisher_factory
from app.services.coding_runs.recorder import CodingRunRecorder
from app.services.coding_runs.review_policy import ReviewPolicy
from app.services.coding_runs.workspace import LocalGitWorkspace

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token")


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after the request."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]
WeaviateResourcesDep = Annotated[WeaviateResources, Depends(get_weaviate_resources)]


def get_repository_store(session: SessionDep) -> RepositoryStore:
    """Build the PostgreSQL store for Git repository records."""
    return RepositoryStore(session)


RepositoryStoreDep = Annotated[RepositoryStore, Depends(get_repository_store)]


def get_repository_document_store(session: SessionDep) -> RepositoryDocumentStore:
    """Build the PostgreSQL store for git document records."""
    return RepositoryDocumentStore(session)


RepositoryDocumentStoreDep = Annotated[RepositoryDocumentStore, Depends(get_repository_document_store)]


def get_document_ingestor(weaviate_resources: WeaviateResourcesDep, repository_document_store: RepositoryDocumentStoreDep) -> DocumentIngestor:
    """Build a lazy repository document ingestor for one request."""
    return DocumentIngestor(weaviate_resources, repository_document_store)


DocumentIngestorDep = Annotated[DocumentIngestor, Depends(get_document_ingestor)]


def get_repository_service(repository_store: RepositoryStoreDep, ingestor: DocumentIngestorDep) -> RepositoryService:
    """Compose the Git repository application service."""
    return RepositoryService(repository_store, ingestor)


RepositoryServiceDep = Annotated[RepositoryService, Depends(get_repository_service)]


def get_repository_session_store(session: SessionDep) -> RepositorySessionStore:
    """Build the PostgreSQL store for repository session records."""
    return RepositorySessionStore(session)


RepositorySessionStoreDep = Annotated[RepositorySessionStore, Depends(get_repository_session_store)]


def get_coding_run_store(session: SessionDep) -> CodingRunStore:
    """Build the PostgreSQL store for Coding Run records."""
    return CodingRunStore(session)


CodingRunStoreDep = Annotated[CodingRunStore, Depends(get_coding_run_store)]


def get_repository_session_service(
    session_store: RepositorySessionStoreDep, repository_store: RepositoryStoreDep, coding_run_store: CodingRunStoreDep
) -> RepositorySessionService:
    """Compose the repository session application service from its stores."""
    return RepositorySessionService(session_store, repository_store, coding_run_store)


RepositorySessionServiceDep = Annotated[RepositorySessionService, Depends(get_repository_session_service)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    """Authenticate an active user from a bearer token.

    Raises:
        HTTPException: If the token or associated user is invalid.

    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        logger.warning("Authentication rejected because the bearer token is invalid")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate credentials")
    user = session.get(User, token_data.sub)
    if not user:
        logger.warning("Authentication rejected because the token user was not found user_id=%s", token_data.sub)
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        logger.warning("Authentication rejected because the user is inactive user_id=%s", user.id)
        raise HTTPException(status_code=400, detail="Inactive user")
    logger.info("User authenticated user_id=%s", user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    """Require and return an authenticated superuser.

    Raises:
        HTTPException: If the current user lacks superuser privileges.

    """
    if not current_user.is_superuser:
        logger.warning("Superuser authorization denied user_id=%s", current_user.id)
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    logger.info("Superuser authorization granted user_id=%s", current_user.id)
    return current_user


def get_openai_llm() -> ChatOpenAI:
    """Build the default streaming chat model (gpt-4o-mini)."""
    return create_chat_model(settings.LLM_MODEL, settings.LLM_MAX_TOKENS, settings.LLM_MAX_RETRIES)


def get_openai_llm_strong() -> ChatOpenAI:
    """Build the strong streaming chat model (gpt-4o)."""
    return create_chat_model(settings.LLM_MODEL_STRONG, settings.STRONG_LLM_MAX_TOKENS, settings.LLM_MAX_RETRIES)


def get_anthropic_llm() -> ChatAnthropic:
    """Build the strongest streaming chat model (Claude Haiku 4.5, via Anthropic)."""
    return create_anthropic_chat_model(settings.LLM_MODEL_STRONGEST, settings.STRONGEST_LLM_MAX_TOKENS, settings.LLM_MAX_RETRIES)


def get_reviewer_fallback_llm() -> ChatOpenAI:
    """Build the Code Reviewer's cross-provider fallback model (gpt-4o-mini, via OpenAI)."""
    return create_chat_model(settings.REVIEWER_FALLBACK_LLM_MODEL, settings.REVIEWER_FALLBACK_LLM_MAX_TOKENS, settings.LLM_MAX_RETRIES)


def get_default_fallback_llm() -> ChatAnthropic:
    """Build the direct default-tier fallback model (Claude Haiku, via Anthropic)."""
    return create_anthropic_chat_model(settings.DEFAULT_LLM_FALLBACK_MODEL, settings.DEFAULT_LLM_FALLBACK_MAX_TOKENS, settings.LLM_MAX_RETRIES)


def get_generator_fallback_llm() -> ChatAnthropic:
    """Build the Code Generator's cross-provider fallback model (Claude Sonnet, via Anthropic)."""
    return create_anthropic_chat_model(settings.STRONG_LLM_FALLBACK_MODEL, settings.STRONG_LLM_FALLBACK_MAX_TOKENS, settings.LLM_MAX_RETRIES)


ChatOpenAIDep = Annotated[ChatOpenAI, Depends(get_openai_llm)]
ChatOpenAIStrongDep = Annotated[ChatOpenAI, Depends(get_openai_llm_strong)]
ChatAnthropicStrongestDep = Annotated[ChatAnthropic, Depends(get_anthropic_llm)]
ChatDefaultFallbackDep = Annotated[ChatAnthropic, Depends(get_default_fallback_llm)]
ChatReviewerFallbackDep = Annotated[ChatOpenAI, Depends(get_reviewer_fallback_llm)]
ChatGeneratorFallbackDep = Annotated[ChatAnthropic, Depends(get_generator_fallback_llm)]


def get_document_retriever(
    current_user: CurrentUser, weaviate_resources: WeaviateResourcesDep, repository_document_store: RepositoryDocumentStoreDep
) -> DocumentRetriever:
    """Build the authenticated user's repository-scoped retriever."""
    reranker = create_reranker()
    return DocumentRetriever(weaviate_resources, str(current_user.id), repository_document_store, reranker)


DocumentRetrieverDep = Annotated[DocumentRetriever, Depends(get_document_retriever)]


def get_session_graph(
    request: Request,
    chat_model: ChatOpenAIDep,
    default_fallback_model: ChatDefaultFallbackDep,
    strong_chat_model: ChatOpenAIStrongDep,
    generator_fallback_model: ChatGeneratorFallbackDep,
    strongest_chat_model: ChatAnthropicStrongestDep,
    reviewer_fallback_model: ChatReviewerFallbackDep,
    document_retriever: DocumentRetrieverDep,
    coding_run_store: CodingRunStoreDep,
    repository_store: RepositoryStoreDep,
):
    """Compile the unified intent-routed graph for one request.

    Classifier and planner reuse the chat model via structured output; retrieval
    and generation reuse the repository-scoped components. This composition root
    chooses every production runtime adapter explicitly: the Coding Run recorder
    persists the code-generation lifecycle, the local checkout workspace factory
    drives Git plumbing, the patch publisher factory publishes approved patches,
    and the durable ``PostgresSaver`` checkpointer (the process-wide singleton
    opened in the application lifespan) holds graph state; only the (in-memory)
    graph wiring is rebuilt per request.
    """
    return build_graph(
        classifier_llm=chat_model,
        default_fallback_llm=default_fallback_model,
        retriever=document_retriever,
        llm=chat_model,
        planner_llm=chat_model,
        code_generator=CodeGenerator(strong_chat_model, fallback_llm=generator_fallback_model),
        code_reviewer=CodeReviewer(strongest_chat_model, fallback_llm=reviewer_fallback_model),
        run_recorder=CodingRunRecorder(coding_run_store),
        workspace_factory=LocalGitWorkspace,
        publisher_factory=build_patch_publisher_factory(repository_store),
        checkpointer=request.app.state.session_checkpointer,
        review_policy=ReviewPolicy.from_settings(),
    )


SessionGraphDep = Annotated[object, Depends(get_session_graph)]
