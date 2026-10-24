"""Unit tests for Module E: Deterministic safety rules catalog."""

from pathlib import Path

from blast_radius.graph.builder import DependencyGraph
from blast_radius.impact.analyzer import ImpactAnalyzer
from blast_radius.models.plan import NormalizedAction, ParsedPlan, ResourceChange
from blast_radius.models.risk import RiskSeverity
from blast_radius.parser.terraform import TerraformPlanParser
from blast_radius.rules.catalog import (
    RuleCriticalResourceDeletion,
    RuleDestructionWithDependents,
    RuleMultipleDestructiveActions,
    RulePlanIntegrityWarnings,
    RuleProtectionRemoval,
    RuleResourceReplacementWithDependents,
    RuleSensitiveAccessModification,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_rule_001_critical_deletion():
    """Verify RULE-001 fires on configured critical resource or production tags."""
    rule = RuleCriticalResourceDeletion()

    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_db_instance.customer_data",
                resource_type="aws_db_instance",
                resource_name="customer_data",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
                before_attributes={"tags": {"Environment": "production", "Criticality": "high"}},
            ),
            ResourceChange(
                address="aws_s3_bucket.audit_archive",
                resource_type="aws_s3_bucket",
                resource_name="audit_archive",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
                before_attributes={},
            ),
        ],
    )

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    # 1. Fire on tag
    findings = rule.evaluate(plan, graph, impact)
    assert len(findings) == 1
    assert findings[0].resource_address == "aws_db_instance.customer_data"
    assert findings[0].severity == RiskSeverity.CRITICAL

    # 2. Fire on explicit critical_resources set
    findings_explicit = rule.evaluate(
        plan, graph, impact, critical_resources={"aws_s3_bucket.audit_archive"}
    )
    assert len(findings_explicit) == 2


def test_rule_002_destruction_with_dependents():
    """Verify RULE-002 flags deleting resources with known dependents."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    rule = RuleDestructionWithDependents()
    findings = rule.evaluate(plan, graph, impact)

    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RULE-002"
    assert f.resource_address == "aws_db_instance.primary"
    assert f.severity in {RiskSeverity.HIGH, RiskSeverity.CRITICAL}


def test_rule_003_replacement_with_dependents():
    """Verify RULE-003 flags forced replacements that cascade downstream."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "replace_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    rule = RuleResourceReplacementWithDependents()
    findings = rule.evaluate(plan, graph, impact)

    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RULE-003"
    assert f.resource_address == "aws_subnet.private_app"
    assert f.severity == RiskSeverity.HIGH


def test_rule_004_multiple_destructive_actions():
    """Verify RULE-004 detects multiple deletions in a single plan."""
    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_instance.worker_1",
                resource_type="aws_instance",
                resource_name="worker_1",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
            ),
            ResourceChange(
                address="aws_instance.worker_2",
                resource_type="aws_instance",
                resource_name="worker_2",
                normalized_action=NormalizedAction.REPLACE,
                is_destructive=True,
            ),
        ],
    )

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    rule = RuleMultipleDestructiveActions()
    findings = rule.evaluate(plan, graph, impact)

    assert len(findings) == 1
    assert findings[0].rule_id == "RULE-004"
    assert findings[0].severity == RiskSeverity.MEDIUM


def test_rule_005_protection_removal():
    """Verify RULE-005 catches disabling deletion_protection."""
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

    rule = RuleProtectionRemoval()
    findings = rule.evaluate(plan, graph, impact)

    assert len(findings) == 1
    assert findings[0].rule_id == "RULE-005"
    assert findings[0].severity == RiskSeverity.CRITICAL


def test_rule_006_sensitive_access_modification():
    """Verify RULE-006 flags opening 0.0.0.0/0 ingress."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "update_resource.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    impact = ImpactAnalyzer(graph).analyze_plan(plan)

    rule = RuleSensitiveAccessModification()
    findings = rule.evaluate(plan, graph, impact)

    assert len(findings) == 1
    assert findings[0].rule_id == "RULE-006"
    assert findings[0].severity == RiskSeverity.HIGH
    assert "0.0.0.0/0" in findings[0].evidence[0]


def test_rule_008_plan_integrity_warnings():
    """Verify RULE-008 flags invalid plans or unsupported actions."""
    invalid_plan = ParsedPlan(
        format_version="1.0",
        warnings=["Failed to parse JSON payload"],
        is_valid=False,
    )
    graph = DependencyGraph()
    impact = ImpactAnalyzer(graph).analyze_plan(invalid_plan)

    rule = RulePlanIntegrityWarnings()
    findings = rule.evaluate(invalid_plan, graph, impact)

    assert len(findings) == 1
    assert findings[0].severity == RiskSeverity.CRITICAL
