"""Unit tests for Module F: Deterministic risk scoring and decision engine."""

from pathlib import Path

from blast_radius.graph.builder import DependencyGraph
from blast_radius.impact.analyzer import ImpactAnalyzer
from blast_radius.models.plan import NormalizedAction, ParsedPlan, ResourceChange
from blast_radius.models.risk import DecisionStatus, RiskSeverity
from blast_radius.parser.terraform import TerraformPlanParser
from blast_radius.scoring.engine import RiskScoringEngine

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_score_calculation_boundary_zero():
    """Verify safe plan yields score=0.0 and PASS status."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "add_resource.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    engine = RiskScoringEngine()
    result = engine.evaluate(plan, graph, impact)

    assert result.risk_score == 0.0
    assert result.decision_status == DecisionStatus.PASS
    assert len(result.findings) == 0


def test_score_calculation_boundary_hundred_capped():
    """Verify extreme danger plan caps at score=100.0 and yields BLOCKED status."""
    # Plan with multiple critical deletions and protection disablement
    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_db_instance.prod_primary",
                resource_type="aws_db_instance",
                resource_name="prod_primary",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
                before_attributes={
                    "tags": {"Environment": "production", "Criticality": "critical"}
                },
            ),
            ResourceChange(
                address="aws_db_instance.prod_replica",
                resource_type="aws_db_instance",
                resource_name="prod_replica",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
                before_attributes={"tags": {"Environment": "production"}},
            ),
            ResourceChange(
                address="aws_db_instance.payment_db",
                resource_type="aws_db_instance",
                resource_name="payment_db",
                normalized_action=NormalizedAction.UPDATE,
                before_attributes={"deletion_protection": True},
                after_attributes={"deletion_protection": False},
            ),
        ],
    )

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    engine = RiskScoringEngine()
    result = engine.evaluate(plan, graph, impact)

    assert result.risk_score == 100.0
    assert result.decision_status == DecisionStatus.BLOCKED
    assert result.severity_counts.get(RiskSeverity.CRITICAL.value, 0) >= 2


def test_score_determinism_identical_runs():
    """Verify that identical inputs produce identical scores, findings, and statuses."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)
    engine = RiskScoringEngine()

    results = [engine.evaluate(plan, graph, impact) for _ in range(5)]

    baseline = results[0]
    for other in results[1:]:
        assert other.risk_score == baseline.risk_score
        assert other.decision_status == baseline.decision_status
        assert other.decision_reason == baseline.decision_reason
        assert len(other.findings) == len(baseline.findings)
        assert [f.id for f in other.findings] == [f.id for f in baseline.findings]


def test_decision_status_blocked_on_critical_finding():
    """Verify any CRITICAL finding triggers BLOCKED status."""
    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_db_instance.main",
                resource_type="aws_db_instance",
                resource_name="main",
                normalized_action=NormalizedAction.UPDATE,
                before_attributes={"deletion_protection": True},
                after_attributes={"deletion_protection": False},
            )
        ],
    )
    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    engine = RiskScoringEngine()
    result = engine.evaluate(plan, graph, impact)

    assert result.decision_status == DecisionStatus.BLOCKED
    assert any(f.severity == RiskSeverity.CRITICAL for f in result.findings)


def test_decision_status_review_required_on_high_finding():
    """Verify HIGH finding (security group opening) triggers REVIEW_REQUIRED."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "update_resource.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    engine = RiskScoringEngine()
    result = engine.evaluate(plan, graph, impact)

    assert result.decision_status == DecisionStatus.REVIEW_REQUIRED
    assert result.risk_score > 0.0


def test_decision_status_incomplete_on_invalid_plan():
    """Verify invalid plan yields ANALYSIS_INCOMPLETE decision."""
    invalid_plan = ParsedPlan(
        format_version="unknown",
        warnings=["Structural parsing failure"],
        is_valid=False,
    )
    graph = DependencyGraph()
    impact = ImpactAnalyzer(graph).analyze_plan(invalid_plan)

    engine = RiskScoringEngine()
    result = engine.evaluate(invalid_plan, graph, impact)

    assert result.decision_status == DecisionStatus.ANALYSIS_INCOMPLETE
    assert "could not be analyzed" in result.decision_reason.lower()
