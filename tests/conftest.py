"""Pytest fixtures and test environment setup."""

import pytest
from fastapi.testclient import TestClient

from blast_radius.api.app import app
from blast_radius.config import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated test settings."""
    return Settings(
        environment="test",
        debug=True,
        log_json=False,
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    """Provide FastAPI test client."""
    # Override settings dependency
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
