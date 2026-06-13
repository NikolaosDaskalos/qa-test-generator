from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import select
from weaviate.classes.config import DataType, Vectorizers

from app import backend_pre_start
from app.backend_pre_start import init, logger
from app.core.config import settings


class FakeCollection:
    def __init__(self, *, multi_tenancy=True, properties=None, vectorizer=Vectorizers.NONE):
        property_types = properties or {backend_pre_start.TEXT_PROPERTY: DataType.TEXT, **dict.fromkeys(backend_pre_start.METADATA_PROPERTIES, DataType.TEXT)}
        self.config = SimpleNamespace(
            get=lambda: SimpleNamespace(
                multi_tenancy_config=SimpleNamespace(enabled=multi_tenancy),
                properties=[SimpleNamespace(name=name, data_type=data_type) for name, data_type in property_types.items()],
                vector_config={"default": SimpleNamespace(vectorizer=SimpleNamespace(vectorizer=vectorizer))},
                vectorizer=None,
            )
        )


class FakeCollections:
    def __init__(self, *, exists=True, collection=None):
        self._exists = exists
        self.collection = collection or FakeCollection()
        self.create_call = None

    def exists(self, name):
        return self._exists

    def create(self, name, **kwargs):
        self.create_call = (name, kwargs)
        self._exists = True

    def get(self, name):
        return self.collection


class FakeClient:
    def __init__(self, collections=None):
        self.collections = collections or FakeCollections()
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


def test_init_successful_connection() -> None:
    engine_mock = MagicMock()

    session_mock = MagicMock()
    session_mock.__enter__.return_value = session_mock

    select1 = select(1)

    with (
        patch("app.backend_pre_start.Session", return_value=session_mock),
        patch("app.backend_pre_start.select", return_value=select1),
        patch.object(logger, "info"),
        patch.object(logger, "error"),
        patch.object(logger, "warn"),
    ):
        try:
            init(engine_mock)
            connection_successful = True
        except Exception:
            connection_successful = False

        assert connection_successful, "The database connection should be successful and not raise an exception."

        session_mock.exec.assert_called_once_with(select1)


def test_main_initializes_database_and_weaviate() -> None:
    with (
        patch.object(backend_pre_start, "init") as init_db_mock,
        patch.object(backend_pre_start, "init_weaviate") as init_weaviate_mock,
        patch.object(backend_pre_start.engine, "dispose") as dispose_mock,
    ):
        backend_pre_start.main()

    init_db_mock.assert_called_once_with(backend_pre_start.engine)
    init_weaviate_mock.assert_called_once_with()
    dispose_mock.assert_called_once_with()


def test_main_disposes_database_engine_when_initialization_fails() -> None:
    with (
        patch.object(backend_pre_start, "init", side_effect=RuntimeError("database unavailable")),
        patch.object(backend_pre_start.engine, "dispose") as dispose_mock,
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        backend_pre_start.main()

    dispose_mock.assert_called_once_with()


def test_init_weaviate_creates_collection_and_closes_client(monkeypatch) -> None:
    collections = FakeCollections(exists=False)
    client = FakeClient(collections)
    monkeypatch.setattr(backend_pre_start, "create_weaviate_client", lambda: client)

    backend_pre_start.init_weaviate()

    collection_name, create_kwargs = collections.create_call
    assert collection_name == settings.WEAVIATE_COLLECTION
    assert create_kwargs["multi_tenancy_config"].enabled is True
    assert [prop.name for prop in create_kwargs["properties"]] == ["content", "source", "repository_id", "parent_id"]
    assert client.close_calls == 1


@pytest.mark.parametrize(
    ("collection", "message"),
    [
        (FakeCollection(multi_tenancy=False), "multi-tenancy"),
        (FakeCollection(properties={backend_pre_start.TEXT_PROPERTY: DataType.INT}), "invalid schema"),
        (FakeCollection(vectorizer=Vectorizers.TEXT2VEC_OPENAI), "self-provided vectors"),
    ],
)
def test_init_weaviate_rejects_invalid_collection_and_closes_client(monkeypatch, collection, message) -> None:
    client = FakeClient(FakeCollections(collection=collection))
    monkeypatch.setattr(backend_pre_start, "create_weaviate_client", lambda: client)

    with pytest.raises(RuntimeError, match=message):
        backend_pre_start.init_weaviate.__wrapped__()

    assert client.close_calls == 1
