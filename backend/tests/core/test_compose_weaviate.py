"""Test the Docker Compose health dependency for Weaviate."""

from pathlib import Path

import yaml

COMPOSE_PATH = Path(__file__).resolve().parents[3] / "compose.yml"


def _compose_services():
    """Load service definitions from the project Compose file."""
    return yaml.safe_load(COMPOSE_PATH.read_text())["services"]


def test_compose_waits_for_healthy_weaviate() -> None:
    """Require application services to wait for a healthy Weaviate."""
    services = _compose_services()

    healthcheck = services["weaviate"]["healthcheck"]
    assert "/v1/.well-known/ready" in " ".join(healthcheck["test"])
    assert "weaviate-init" not in services

    for service_name in ("prestart", "backend"):
        dependency = services[service_name]["depends_on"]["weaviate"]
        assert dependency["condition"] == "service_healthy"
