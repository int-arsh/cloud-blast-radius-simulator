"""Unit tests for FastAPI health check and error handling."""

from fastapi import status
from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """Verify /health returns HTTP 200 with service metadata."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Cloud Blast-Radius Simulator"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


def test_openapi_docs_accessible(client: TestClient):
    """Verify OpenAPI documentation endpoint is reachable."""
    response = client.get("/docs")
    assert response.status_code == status.HTTP_200_OK


def test_cors_headers(client: TestClient):
    """Verify CORS headers are present on requests."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
