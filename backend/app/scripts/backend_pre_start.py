"""Pre-start gate: block until Postgres and Weaviate are ready before the app boots."""

import logging
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed
from weaviate.classes.config import Configure, DataType, Property, Vectorizers
from weaviate.client import WeaviateClient

from app.core import settings
from app.db import engine
from app.integrations.weaviate import METADATA_PROPERTIES, TEXT_PROPERTY, create_weaviate_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1


@retry(stop=stop_after_attempt(max_tries), wait=wait_fixed(wait_seconds), before=before_log(logger, logging.INFO), after=after_log(logger, logging.WARN))
def init(db_engine: Engine) -> None:
    """Wait until the database accepts a query."""
    try:
        with Session(db_engine) as session:
            # Try to create session to check if DB is awake
            session.exec(select(1))
            logger.info("Database readiness check succeeded")
    except Exception as e:
        logger.error("Database readiness check failed: %s", e)
        raise e


@retry(stop=stop_after_attempt(max_tries), wait=wait_fixed(wait_seconds), before=before_log(logger, logging.INFO), after=after_log(logger, logging.WARN))
def init_weaviate() -> None:
    """Wait for Weaviate, create its collection when absent, and validate it."""
    client = create_weaviate_client()
    try:
        _get_or_create_collection(client)
        logger.info("Weaviate readiness check succeeded collection=%s", settings.WEAVIATE_COLLECTION)
    except Exception as exc:
        logger.error("Weaviate readiness check failed: %s", exc)
        raise
    finally:
        client.close()


def _get_or_create_collection(client: WeaviateClient) -> None:
    """Create the configured collection when absent, then validate it."""
    if not client.collections.exists(settings.WEAVIATE_COLLECTION):
        logger.info("Creating Weaviate collection=%s", settings.WEAVIATE_COLLECTION)
        client.collections.create(
            settings.WEAVIATE_COLLECTION,
            properties=[Property(name=TEXT_PROPERTY, data_type=DataType.TEXT), *[Property(name=name, data_type=DataType.TEXT) for name in METADATA_PROPERTIES]],
            vector_config=Configure.Vectors.self_provided(),
            multi_tenancy_config=Configure.multi_tenancy(enabled=True),
        )
        logger.info("Weaviate collection created collection=%s", settings.WEAVIATE_COLLECTION)
    else:
        logger.info("Weaviate collection already exists collection=%s", settings.WEAVIATE_COLLECTION)

    collection = client.collections.get(settings.WEAVIATE_COLLECTION)
    _validate_collection(collection)


def _validate_collection(collection: Any) -> None:
    """Validate collection tenancy, properties, and vectorizer settings."""
    config = collection.config.get()
    if not config.multi_tenancy_config.enabled:
        logger.error("Weaviate collection validation failed because multi-tenancy is disabled collection=%s", settings.WEAVIATE_COLLECTION)
        raise RuntimeError(f"Weaviate collection {settings.WEAVIATE_COLLECTION!r} must enable multi-tenancy")

    properties = {prop.name: prop.data_type for prop in config.properties}
    expected_properties = {TEXT_PROPERTY: DataType.TEXT, **dict.fromkeys(METADATA_PROPERTIES, DataType.TEXT)}
    invalid_properties = [name for name, expected_type in expected_properties.items() if properties.get(name) != expected_type]
    if invalid_properties:
        logger.error("Weaviate collection validation failed invalid_properties=%s", invalid_properties)
        raise RuntimeError(f"Weaviate collection {settings.WEAVIATE_COLLECTION!r} has an invalid schema for properties: {', '.join(invalid_properties)}")

    vectorizers: list[Any] = []
    if config.vector_config:
        vectorizers.extend(named_vector.vectorizer.vectorizer for named_vector in config.vector_config.values())
    elif config.vectorizer is not None:
        vectorizers.append(config.vectorizer)

    if not vectorizers or any(vectorizer not in (Vectorizers.NONE, Vectorizers.NONE.value) for vectorizer in vectorizers):
        logger.error("Weaviate collection validation failed because vectorizer configuration is invalid collection=%s", settings.WEAVIATE_COLLECTION)
        raise RuntimeError(f"Weaviate collection {settings.WEAVIATE_COLLECTION!r} must use self-provided vectors")
    logger.info("Weaviate collection validation succeeded collection=%s", settings.WEAVIATE_COLLECTION)


def main() -> None:
    """Run the database and Weaviate readiness checks, then dispose the engine."""
    logger.info("Initializing service")
    try:
        init(engine)
        init_weaviate()
        logger.info("Service finished initializing")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
