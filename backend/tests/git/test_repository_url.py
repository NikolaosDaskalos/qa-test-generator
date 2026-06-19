import pytest

from app.git import SUPPORTED_REPOSITORY_HOSTS, parse_repository_url


def test_ssh_and_https_urls_have_the_same_canonical_identity() -> None:
    ssh = parse_repository_url("git@github.com:openai/openai-python.git")
    https = parse_repository_url("https://github.com/openai/openai-python")

    assert ssh.canonical_url == "https://github.com/openai/openai-python.git"
    assert ssh.canonical_url == https.canonical_url


def test_repository_url_supports_github() -> None:
    parsed = parse_repository_url("git@github.com:openai/openai-python.git")

    assert parsed.host == "github.com"
    assert parsed.canonical_url == "https://github.com/openai/openai-python.git"
    assert parsed.host in SUPPORTED_REPOSITORY_HOSTS


def test_repository_url_rejects_gitlab() -> None:
    with pytest.raises(ValueError, match="provider is not supported"):
        parse_repository_url("git@gitlab.com:group/repository.git")


def test_repository_url_rejects_bitbucket() -> None:
    with pytest.raises(ValueError, match="provider is not supported"):
        parse_repository_url("https://bitbucket.org/team/repository.git")


def test_repository_url_rejects_missing_repository_name() -> None:
    with pytest.raises(ValueError, match="not valid"):
        parse_repository_url("https://github.com/openai")


@pytest.mark.parametrize("repo_url", ["https://example.com/team/repository.git", "https://github.com:8443/team/repository.git"])
def test_repository_url_rejects_unsupported_domains_and_custom_ports(repo_url: str) -> None:
    with pytest.raises(ValueError, match="provider is not supported"):
        parse_repository_url(repo_url)
