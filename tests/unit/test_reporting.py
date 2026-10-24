"""Unit tests for Module G: JSON and Markdown report generators."""

from blast_radius.models.impact import ImpactAnalysisReport
from blast_radius.models.plan import NormalizedAction
from blast_radius.models.report import FullAnalysisReport
from blast_radius.models.risk import (
    DecisionStatus,
    RiskFinding,
    RiskScoreBreakdown,
    RiskSeverity,
)
from blast_radius.reporting.json_reporter import JsonReporter
from blast_radius.reporting.markdown_reporter import MarkdownReporter


def test_json_reporter_serialization():
    """Verify JsonReporter produces valid JSON with secret masking."""
    report = FullAnalysisReport(
        analysis_id="sim-test-1234",
        timestamp="2026-10-25T00:00:00Z",
        engine_version="0.1.0",
        format_version="1.2",
        terraform_version="1.5.7",
        decision_status=DecisionStatus.PASS,
        decision_reason="No risks detected.",
        risk_score=0.0,
        score_breakdown=RiskScoreBreakdown(
            base_score=0.0,
            blast_radius_multiplier=1.0,
            confidence_factor=1.0,
            final_score=0.0,
            formula="Clean plan.",
        ),
        resource_counts={"total": 2, "changed": 1, "unaffected": 1},
        action_counts={"create": 1},
        dependency_counts={"nodes": 2, "edges": 0, "cycles": 0},
        severity_counts={},
        impact_summary=ImpactAnalysisReport(
            total_changed_resources=1,
            total_impacted_resources=0,
            direct_impact_count=0,
            transitive_impact_count=0,
            unaffected_resource_count=1,
            resource_blast_radii=[],
            unique_impacted_addresses=[],
            missing_information_warnings=[],
            has_destructive_impact=False,
        ),
        findings=[],
        warnings=[],
        remediations=[],
        metadata={"admin_password": "supersecretpassword"},  # Sensitive key
    )

    data = JsonReporter.generate_dict(report)
    assert data["analysis_id"] == "sim-test-1234"
    assert data["metadata"]["admin_password"] == "[REDACTED]"

    json_str = JsonReporter.generate_json(report)
    assert "sim-test-1234" in json_str
    assert "supersecretpassword" not in json_str


def test_markdown_reporter_rendering():
    """Verify MarkdownReporter generates clean formatted Markdown document."""
    finding = RiskFinding(
        id="FINDING-RULE-002-aws_db_instance.primary",
        rule_id="RULE-002",
        rule_name="Destruction of Resource with Known Dependents",
        severity=RiskSeverity.HIGH,
        resource_address="aws_db_instance.primary",
        proposed_action=NormalizedAction.DELETE,
        evidence=["2 downstream dependents"],
        reasoning="Deleting database breaks dependent services.",
        remediation="Migrate dependents before deletion.",
        limitations="Based on verified references.",
    )

    report = FullAnalysisReport(
        analysis_id="sim-test-5678",
        timestamp="2026-10-25T00:00:00Z",
        engine_version="0.1.0",
        format_version="1.2",
        terraform_version="1.5.7",
        decision_status=DecisionStatus.REVIEW_REQUIRED,
        decision_reason="Manual review required due to HIGH severity findings.",
        risk_score=35.0,
        score_breakdown=RiskScoreBreakdown(
            base_score=20.0,
            blast_radius_multiplier=1.75,
            confidence_factor=1.0,
            final_score=35.0,
            formula="base(20) * 1.75 = 35.0",
        ),
        resource_counts={"total": 3, "changed": 1, "unaffected": 0},
        action_counts={"delete": 1},
        dependency_counts={"nodes": 3, "edges": 2, "cycles": 0},
        severity_counts={"high": 1},
        impact_summary=ImpactAnalysisReport(
            total_changed_resources=1,
            total_impacted_resources=2,
            direct_impact_count=2,
            transitive_impact_count=0,
            unaffected_resource_count=0,
            resource_blast_radii=[],
            unique_impacted_addresses=["aws_ecs_service.api", "aws_route53_record.db"],
            missing_information_warnings=[],
            has_destructive_impact=True,
        ),
        findings=[finding],
        warnings=["Sample warning"],
        remediations=["Migrate dependents before deletion."],
    )

    md = MarkdownReporter.generate_markdown(report)

    assert "# Cloud Blast-Radius Simulation Report: [REVIEW REQUIRED]" in md
    assert "35.0 / 100.0" in md
    assert "aws_db_instance.primary" in md
    assert "RULE-002" in md
    assert "MANUAL REVIEW" in md
    assert "Sample warning" in md
