"""Unit tests for Module D: Impact analysis and blast radius engine."""

from pathlib import Path

from blast_radius.graph.builder import DependencyGraph
from blast_radius.impact.analyzer import ImpactAnalyzer
from blast_radius.models.graph import (
    ConfidenceLevel,
    DependencyEdge,
    EvidenceCategory,
    ResourceNode,
)
from blast_radius.models.impact import ImpactType
from blast_radius.models.plan import NormalizedAction, ParsedPlan, ResourceChange
from blast_radius.parser.terraform import TerraformPlanParser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_impact_delete_with_dependents():
    """Verify deleting a database correctly calculates direct dependents and failure scenarios."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    assert report.total_changed_resources == 1  # Only DB has active change
    assert report.total_impacted_resources == 2  # ECS service and Route 53 record
    assert report.direct_impact_count == 2
    assert report.transitive_impact_count == 0
    assert report.has_destructive_impact is True
    assert set(report.unique_impacted_addresses) == {
        "aws_ecs_service.api",
        "aws_route53_record.db",
    }

    db_radius = report.resource_blast_radii[0]
    assert db_radius.resource_address == "aws_db_instance.primary"
    assert db_radius.action == NormalizedAction.DELETE
    assert db_radius.is_destructive is True

    # Check failure scenario details
    for impacted in db_radius.impacted_resources:
        assert impacted.impact_type == ImpactType.DIRECT
        assert impacted.path_length == 1
        assert "database tier" in impacted.potential_failure_scenario.lower()
        assert impacted.confidence == ConfidenceLevel.VERIFIED


def test_impact_replace_with_dependents():
    """Verify replacing a subnet correctly identifies downstream compute instances."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "replace_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    assert report.total_changed_resources == 1
    assert report.total_impacted_resources == 1
    assert report.unique_impacted_addresses == ["aws_instance.app"]
    assert report.has_destructive_impact is True

    radius = report.resource_blast_radii[0]
    assert radius.action == NormalizedAction.REPLACE
    assert radius.is_destructive is True

    impacted = radius.impacted_resources[0]
    assert impacted.address == "aws_instance.app"
    assert "network infrastructure" in impacted.potential_failure_scenario.lower()


def test_impact_isolated_deletion():
    """Verify deleting an isolated resource results in zero downstream impact."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_isolated.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    assert report.total_changed_resources == 1
    assert report.total_impacted_resources == 0
    assert len(report.unique_impacted_addresses) == 0

    radius = report.resource_blast_radii[0]
    assert radius.total_impacted_count == 0
    assert "isolated" in radius.summary.lower()


def test_impact_new_addition_no_dependents():
    """Verify adding a new resource causes zero downstream disruption."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "add_resource.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    assert report.total_changed_resources == 1
    assert report.total_impacted_resources == 0
    radius = report.resource_blast_radii[0]
    assert radius.action == NormalizedAction.CREATE
    assert radius.total_impacted_count == 0
    assert "new addition" in radius.summary.lower()


def test_multi_tier_transitive_impact():
    """Verify multi-tier downstream impact propagation: Storefront -> API -> Database."""
    graph = DependencyGraph()
    for addr, rtype in [
        ("aws_s3_bucket.storefront", "aws_s3_bucket"),
        ("aws_ecs_service.api", "aws_ecs_service"),
        ("aws_db_instance.db", "aws_db_instance"),
    ]:
        graph.add_resource_node(
            ResourceNode(address=addr, resource_type=rtype, resource_name=addr.split(".")[1])
        )

    # Storefront -> API
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_s3_bucket.storefront",
            target="aws_ecs_service.api",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.api_url",
        )
    )
    # API -> Database
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_ecs_service.api",
            target="aws_db_instance.db",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.db_endpoint",
        )
    )

    # Proposed change: Delete Database
    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_db_instance.db",
                resource_type="aws_db_instance",
                resource_name="db",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
                raw_actions=["delete"],
            )
        ],
    )

    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    assert report.total_impacted_resources == 2
    assert report.direct_impact_count == 1  # API
    assert report.transitive_impact_count == 1  # Storefront

    radius = report.resource_blast_radii[0]
    by_addr = {imp.address: imp for imp in radius.impacted_resources}

    api_imp = by_addr["aws_ecs_service.api"]
    assert api_imp.impact_type == ImpactType.DIRECT
    assert api_imp.path_length == 1
    assert api_imp.shortest_path == ["aws_ecs_service.api", "aws_db_instance.db"]

    storefront_imp = by_addr["aws_s3_bucket.storefront"]
    assert storefront_imp.impact_type == ImpactType.TRANSITIVE
    assert storefront_imp.path_length == 2
    assert storefront_imp.shortest_path == [
        "aws_s3_bucket.storefront",
        "aws_ecs_service.api",
        "aws_db_instance.db",
    ]


def test_prevent_false_positive_impacts_on_unrelated_resources():
    """Verify unrelated infrastructure resources are never marked as impacted."""
    graph = DependencyGraph()

    # Subsystem A: App -> DB
    graph.add_resource_node(
        ResourceNode(address="aws_instance.app", resource_type="aws_instance", resource_name="app")
    )
    graph.add_resource_node(
        ResourceNode(
            address="aws_db_instance.db", resource_type="aws_db_instance", resource_name="db"
        )
    )
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_instance.app",
            target="aws_db_instance.db",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.db_id",
        )
    )

    # Subsystem B: Billing service -> Billing DB (completely separate)
    graph.add_resource_node(
        ResourceNode(
            address="aws_instance.billing",
            resource_type="aws_instance",
            resource_name="billing",
        )
    )
    graph.add_resource_node(
        ResourceNode(
            address="aws_db_instance.billing_db",
            resource_type="aws_db_instance",
            resource_name="billing_db",
        )
    )
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_instance.billing",
            target="aws_db_instance.billing_db",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.billing_db_id",
        )
    )

    # Change: Delete DB in Subsystem A
    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_db_instance.db",
                resource_type="aws_db_instance",
                resource_name="db",
                normalized_action=NormalizedAction.DELETE,
                is_destructive=True,
            )
        ],
    )

    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    # Only aws_instance.app should be impacted!
    assert report.total_impacted_resources == 1
    assert report.unique_impacted_addresses == ["aws_instance.app"]
    assert "aws_instance.billing" not in report.unique_impacted_addresses
    assert "aws_db_instance.billing_db" not in report.unique_impacted_addresses
    assert report.unaffected_resource_count == 2


def test_changing_dependent_does_not_impact_dependency():
    """Verify changing an app does NOT impact the database it depends upon."""
    graph = DependencyGraph()
    graph.add_resource_node(
        ResourceNode(address="aws_instance.app", resource_type="aws_instance", resource_name="app")
    )
    graph.add_resource_node(
        ResourceNode(
            address="aws_db_instance.db", resource_type="aws_db_instance", resource_name="db"
        )
    )
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_instance.app",
            target="aws_db_instance.db",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.db_id",
        )
    )

    # Proposed change: Update or Replace the APP
    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_instance.app",
                resource_type="aws_instance",
                resource_name="app",
                normalized_action=NormalizedAction.REPLACE,
                is_destructive=True,
            )
        ],
    )

    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    # The DB does NOT depend on the app, so DB is NOT impacted
    assert report.total_impacted_resources == 0
    assert "aws_db_instance.db" not in report.unique_impacted_addresses


def test_missing_information_warning_propagation():
    """Verify missing unmanaged targets generate explicit incomplete-analysis warnings."""
    graph = DependencyGraph()
    graph.add_resource_node(
        ResourceNode(address="aws_instance.app", resource_type="aws_instance", resource_name="app")
    )
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_instance.app",
            target="aws_vpc.external_unmanaged_vpc",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.vpc_id",
        )
    )

    plan = ParsedPlan(
        format_version="1.2",
        resource_changes=[
            ResourceChange(
                address="aws_instance.app",
                resource_type="aws_instance",
                resource_name="app",
                normalized_action=NormalizedAction.UPDATE,
            )
        ],
    )

    analyzer = ImpactAnalyzer(graph)
    report = analyzer.analyze_plan(plan)

    assert len(report.missing_information_warnings) > 0
    assert any("external_unmanaged_vpc" in w for w in report.missing_information_warnings)
