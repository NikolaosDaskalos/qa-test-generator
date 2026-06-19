"""Configure the FastAPI application and process-wide resource lifecycle."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.exception_handlers import register_exception_handlers
from app.core import close_checkpointer, open_checkpointer, settings, vector_db

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    """Build a stable OpenAPI operation ID from the route tag and name."""
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)
    logger.info("Sentry monitoring initialized for environment=%s", settings.ENVIRONMENT)
else:
    logger.info("Sentry monitoring disabled for environment=%s", settings.ENVIRONMENT)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize Weaviate and the session-graph checkpointer at startup; close both on shutdown."""
    logger.info("Application startup started")
    vector_db.initialize_weaviate()
    checkpointer, checkpointer_pool = open_checkpointer()
    app.state.session_checkpointer = checkpointer
    logger.info("Application startup completed")
    try:
        yield
    finally:
        logger.info("Application shutdown started")
        close_checkpointer(checkpointer_pool)
        vector_db.close_weaviate()
        logger.info("Application shutdown completed")


app = FastAPI(
    title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json", generate_unique_id_function=custom_generate_unique_id, lifespan=lifespan
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.all_cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    logger.info("CORS middleware configured with origin_count=%s", len(settings.all_cors_origins))

app.include_router(api_router, prefix=settings.API_V1_STR)
logger.info("API router registered with prefix=%s", settings.API_V1_STR)

register_exception_handlers(app)
logger.info("Domain exception handlers registered")
