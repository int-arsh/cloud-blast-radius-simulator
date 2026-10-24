"""Integration tests for FastAPI endpoints (/api/v1/analyze and /api/v1/analyze/export)."""

from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_api_analyze_json_body(client: TestClient):
    """Verify POST /api/v1/analyze with JSON body returns FullAnalysisReport."""
    plan_bytes = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    response = client.post(
        "/api/v1/analyze",
        content=plan_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "analysis_id" in data
    assert data["decision_status"] in {"review_required", "blocked"}
    assert data["risk_score"] > 0.0
    assert data["resource_counts"]["changed"] == 1
    assert data["impact_summary"]["total_impacted_resources"] == 2
    assert len(data["findings"]) >= 1


def test_api_analyze_file_upload(client: TestClient):
    """Verify POST /api/v1/analyze with multipart file upload."""
    plan_path = FIXTURES_DIR / "add_resource.json"
    with open(plan_path, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("add_resource.json", f, "application/json")},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision_status"] == "pass"
    assert data["risk_score"] == 0.0
    assert data["resource_counts"]["changed"] == 1
    assert data["impact_summary"]["total_impacted_resources"] == 0


def test_api_analyze_with_critical_resources_param(client: TestClient):
    """Verify query parameter ?critical_resources triggers RULE-001 and BLOCKED status."""
    plan_bytes = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    response = client.post(
        "/api/v1/analyze?critical_resources=aws_db_instance.primary",
        content=plan_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision_status"] == "blocked"
    assert any(f["rule_id"] == "RULE-001" for f in data["findings"])


def test_api_export_markdown(client: TestClient):
    """Verify POST /api/v1/analyze/export?format=markdown returns formatted Markdown."""
    plan_bytes = (FIXTURES_DIR / "replace_with_dependents.json").read_bytes()
    response = client.post(
        "/api/v1/analyze/export?format=markdown",
        content=plan_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/markdown")
    content = response.text
    assert "# Cloud Blast-Radius Simulation Report" in content
    assert "aws_subnet.private_app" in content


def test_api_export_json(client: TestClient):
    """Verify POST /api/v1/analyze/export?format=json returns clean JSON."""
    plan_bytes = (FIXTURES_DIR / "delete_isolated.json").read_bytes()
    response = client.post(
        "/api/v1/analyze/export?format=json",
        content=plan_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "analysis_id" in data
    assert "decision_status" in data


def test_api_empty_payload_error(client: TestClient):
    """Verify empty request body returns HTTP 400 Bad Request."""
    response = client.post(
        "/api/v1/analyze",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "No plan payload provided" in response.json()["detail"]


def test_api_oversized_payload_error(client: TestClient):
    """Verify payload exceeding size limit returns HTTP 413 Entity Too Large."""
    oversized = b"x" * (11 * 1024 * 1024)  # 11 MB exceeds 10 MB limit
    response = client.post(
        "/api/v1/analyze",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


def test_api_malformed_plan_returns_incomplete_status(client: TestClient):
    """Verify malformed JSON returns 200 with analysis_incomplete status without crashing."""
    malformed_bytes = (FIXTURES_DIR / "malformed.json").read_bytes()
    response = client.post(
        "/api/v1/analyze",
        content=malformed_bytes,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["decision_status"] == "analysis_incomplete"
    assert len(data["warnings"]) > 0
