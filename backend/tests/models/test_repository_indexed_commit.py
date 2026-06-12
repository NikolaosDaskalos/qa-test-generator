"""Test Repository indexed-commit model metadata."""

from typing import Any, cast

from app.models.repository import Repository


def test_repository_indexed_commit_is_nullable_and_sha_sized() -> None:
    repository_table = cast(Any, Repository).__table__
    indexed_commit_column = repository_table.c.indexed_commit_sha

    assert indexed_commit_column.nullable
    assert indexed_commit_column.type.length == 40
