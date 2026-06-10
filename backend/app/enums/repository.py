from enum import Enum


class RepositoryProvider(str, Enum):
    github = "github"
    gitlab = "gitlab"
    bitbucket = "bitbucket"


class RepositoryStatus(str, Enum):
    pending = "pending"
    cloning = "cloning"
    cloned = "cloned"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"
