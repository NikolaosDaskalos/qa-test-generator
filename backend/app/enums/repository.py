"""Enumerations for Git repositories: hosting provider and indexing status."""

from enum import Enum


class RepositoryProvider(str, Enum):
    """Supported Git hosting providers."""

    github = "github"


class RepositoryStatus(str, Enum):
    """Lifecycle of a repository from registration through clone, index, and ready."""

    pending = "pending"
    cloning = "cloning"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"
