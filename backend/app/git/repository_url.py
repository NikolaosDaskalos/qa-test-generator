"""Validate repository URLs and convert them to a canonical HTTPS identity.

Only explicitly supported hosted Git providers are accepted. Canonical URLs
are safe to persist and compare because credentials, query strings, fragments,
and alternate SSH syntax are removed.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import giturlparse  # type: ignore[import-untyped]
from giturlparse import GitUrlParsed

logger = logging.getLogger(__name__)

SUPPORTED_REPOSITORY_HOSTS = frozenset({"github.com"})


@dataclass(frozen=True)
class ParsedRepositoryUrl:
    """Validated repository identity used by persistence and Git operations.

    Attributes:
        canonical_url: Credential-free HTTPS URL used for cloning and equality.
        host: Supported provider hostname, such as ``github.com``.
        owner: Provider-specific account or namespace that owns the repository.
        name: Repository name as reported by ``giturlparse``.

    """

    canonical_url: str
    host: str
    owner: str
    name: str


def parse_repository_url(repo_url: str) -> ParsedRepositoryUrl:
    """Validate and normalize a Git repository URL.

    SSH and HTTPS forms of the same repository produce the same canonical
    identity. Custom hosts and custom ports are rejected by the provider
    allowlist.

    Args:
        repo_url: User-supplied SSH or HTTPS repository URL.

    Returns:
        A validated, credential-free repository identity.

    Raises:
        ValueError: If the URL is empty, malformed, or uses an unsupported host.

    """
    if not repo_url or not repo_url.strip():
        logger.warning("Repository URL validation failed because the value is empty")
        raise ValueError("Repository URL cannot be empty")

    parsed: GitUrlParsed = giturlparse.parse(repo_url.strip())
    if not parsed.valid:
        logger.warning("Repository URL validation failed because the value is malformed")
        raise ValueError("Repository URL is not valid")

    host = parsed.host.lower()
    if host not in SUPPORTED_REPOSITORY_HOSTS:
        logger.warning("Repository URL validation rejected unsupported host=%s", host)
        raise ValueError("Repository provider is not supported")

    split_url = urlsplit(parsed.url2https)
    canonical_url = urlunsplit(("https", host, split_url.path.rstrip("/"), "", ""))
    logger.info("Repository URL validated host=%s owner=%s repository=%s", host, parsed.owner, parsed.name)
    return ParsedRepositoryUrl(canonical_url=canonical_url, host=host, owner=parsed.owner, name=parsed.name)
