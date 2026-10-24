"""Integration tests for BlastRadiusPipeline processing complete fixtures."""

from pathlib import Path

from blast_radius.models.risk import DecisionStatus
from blast_radius.pipeline import BlastRadiusPipeline
from blast_radius.reporting.json_reporter import JsonReporter
from blast_radius.reporting.markdown_reporter import MarkdownReporter

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_pipeline_complete_destructive_scenario():
    """Verify end-to-end pipeline processing on delete_with_dependents fixture."""
    pipeline = BlastRadiusPipeline()
    plan_bytes = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()

    report = pipeline.run_analysis(plan_bytes)

    assert report.decision_status in {DecisionStatus.REVIEW_REQUIRED, DecisionStatus.BLOCKED}
    assert report.risk_score > 0.0
    assert report.resource_counts["changed"] == 1
    assert report.impact_summary.total_impacted_resources == 2
    assert report.dependency_counts["edges"] == 2
    assert len(report.findings) >= 1

    # Verify JSON output
    json_output = JsonReporter.generate_json(report)
    assert report.analysis_id in json_output

    # Verify Markdown output
    markdown_output = MarkdownReporter.generate_markdown(report)
    assert "# Cloud Blast-Radius Simulation Report" in markdown_output
    assert "aws_db_instance.primary" in markdown_output


def test_pipeline_sensitive_values_safety():
    """Verify secrets in before/after attributes are completely masked in pipeline reports."""
    pipeline = BlastRadiusPipeline()
    plan_bytes = (FIXTURES_DIR / "sensitive_values.json").read_bytes()

    report = pipeline.run_analysis(plan_bytes)
    json_output = JsonReporter.generate_json(report)
    markdown_output = MarkdownReporter.generate_markdown(report)

    # Prove that plain text secrets never leak into generated reports
    assert "PlainTextOldPassword123!" not in json_output
    assert "PlainTextNewPassword456!" not in json_output
    assert "live_tok_9988776655" not in json_output
    assert "live_tok_1122334455" not in json_output

    assert "PlainTextOldPassword123!" not in markdown_output
    assert "PlainTextNewPassword456!" not in markdown_output


def test_pipeline_cyclic_graph_graceful_handling():
    """Verify pipeline completes cleanly on circular dependencies with warnings recorded."""
    pipeline = BlastRadiusPipeline()
    plan_bytes = (FIXTURES_DIR / "cyclic_dependency.json").read_bytes()

    report = pipeline.run_analysis(plan_bytes)

    assert report.decision_status != DecisionStatus.ANALYSIS_INCOMPLETE
    assert report.dependency_counts["cycles"] == 1
    assert any("cycle detected" in w.lower() for w in report.warnings)
