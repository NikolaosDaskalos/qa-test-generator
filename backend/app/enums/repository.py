from enum import Enum


class RepositoryProvider(str, Enum):
    github = "github"


class RepositoryStatus(str, Enum):
    pending = "pending"
    cloning = "cloning"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"
