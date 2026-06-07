import pytest

from app.git.repository_url import (
    SUPPORTED_REPOSITORY_HOSTS,
    parse_repository_url,
)


def test_ssh_and_https_urls_have_the_same_canonical_identity() -> None:
    ssh = parse_repository_url("git@github.com:openai/openai-python.git")
    https = parse_repository_url("https://github.com/openai/openai-python")

    assert ssh.canonical_url == "https://github.com/openai/openai-python.git"
    assert ssh.canonical_url == https.canonical_url


@pytest.mark.parametrize(
    ("repo_url", "host", "canonical_url"),
    [
        (
            "git@github.com:openai/openai-python.git",
            "github.com",
            "https://github.com/openai/openai-python.git",
        ),
        (
            "git@gitlab.com:group/repository.git",
            "gitlab.com",
            "https://gitlab.com/group/repository.git",
        ),
        (
            "https://bitbucket.org/team/repository.git",
            "bitbucket.org",
            "https://bitbucket.org/team/repository.git",
        ),
    ],
)
def test_repository_url_supports_known_providers(
    repo_url: str,
    host: str,
    canonical_url: str,
) -> None:
    parsed = parse_repository_url(repo_url)

    assert parsed.host == host
    assert parsed.canonical_url == canonical_url
    assert parsed.host in SUPPORTED_REPOSITORY_HOSTS


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://example.com/team/repository.git",
        "https://github.com:8443/team/repository.git",
    ],
)
def test_repository_url_rejects_unsupported_domains_and_custom_ports(
    repo_url: str,
) -> None:
    with pytest.raises(ValueError, match="provider is not supported"):
        parse_repository_url(repo_url)
