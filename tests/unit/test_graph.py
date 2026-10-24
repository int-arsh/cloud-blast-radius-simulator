"""Unit tests for Module C: Infrastructure dependency graph engine."""

from pathlib import Path

from blast_radius.graph.builder import DependencyGraph
from blast_radius.models.graph import (
    ConfidenceLevel,
    DependencyEdge,
    EvidenceCategory,
    ResourceNode,
)
from blast_radius.parser.terraform import TerraformPlanParser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_dependency_direction():
    """Verify directed edge convention: App -> Database means App depends on Database."""
    graph = DependencyGraph()
    graph.add_resource_node(
        ResourceNode(
            address="aws_ecs_service.app",
            resource_type="aws_ecs_service",
            resource_name="app",
        )
    )
    graph.add_resource_node(
        ResourceNode(
            address="aws_db_instance.db",
            resource_type="aws_db_instance",
            resource_name="db",
        )
    )

    # Add edge: App -> Database
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_ecs_service.app",
            target="aws_db_instance.db",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            confidence=ConfidenceLevel.VERIFIED,
            provenance="config.expressions.db_endpoint",
        )
    )

    # Querying App: what does it depend upon?
    assert graph.get_direct_dependencies("aws_ecs_service.app") == ["aws_db_instance.db"]
    assert graph.get_direct_dependents("aws_ecs_service.app") == []

    # Querying Database: what depends upon it? (impacted if DB changes)
    assert graph.get_direct_dependents("aws_db_instance.db") == ["aws_ecs_service.app"]
    assert graph.get_direct_dependencies("aws_db_instance.db") == []


def test_transitive_dependency_traversal():
    """Verify multi-tier downstream impact traversal: Frontend -> API -> Database."""
    graph = DependencyGraph()
    for addr, rtype in [
        ("aws_s3_bucket.frontend", "aws_s3_bucket"),
        ("aws_ecs_service.api", "aws_ecs_service"),
        ("aws_db_instance.db", "aws_db_instance"),
    ]:
        graph.add_resource_node(
            ResourceNode(address=addr, resource_type=rtype, resource_name=addr.split(".")[1])
        )

    # Frontend -> API
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_s3_bucket.frontend",
            target="aws_ecs_service.api",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="api_url",
        )
    )
    # API -> Database
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_ecs_service.api",
            target="aws_db_instance.db",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="db_endpoint",
        )
    )

    # If Database is changed/destroyed, both API (direct) and Frontend (transitive) are affected
    direct_dependents = graph.get_direct_dependents("aws_db_instance.db")
    assert direct_dependents == ["aws_ecs_service.api"]

    transitive_dependents = graph.get_transitive_dependents("aws_db_instance.db")
    assert transitive_dependents == {"aws_ecs_service.api", "aws_s3_bucket.frontend"}

    # Impact path verification
    paths = graph.get_impact_paths("aws_s3_bucket.frontend", "aws_db_instance.db")
    assert paths == [["aws_s3_bucket.frontend", "aws_ecs_service.api", "aws_db_instance.db"]]


def test_isolated_resource_detection():
    """Verify resources with zero edges are identified as isolated."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_isolated.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analysis = graph.analyze()

    assert analysis.total_nodes == 1
    assert analysis.total_edges == 0
    assert "aws_cloudwatch_log_group.dev_debug" in analysis.isolated_nodes
    assert len(graph.get_direct_dependents("aws_cloudwatch_log_group.dev_debug")) == 0


def test_cycle_detection_safety():
    """Verify cyclic dependency graphs are detected without infinite recursion."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "cyclic_dependency.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analysis = graph.analyze()

    assert len(analysis.cycles) == 1
    cycle = analysis.cycles[0]
    assert set(cycle.nodes) == {"aws_security_group.sg_a", "aws_security_group.sg_b"}

    # Traversing dependents on cyclic graph completes safely without hanging
    deps_a = graph.get_transitive_dependents("aws_security_group.sg_a")
    assert "aws_security_group.sg_b" in deps_a


def test_missing_dependency_provenance():
    """Verify references to resources absent from plan are recorded as missing dependencies."""
    graph = DependencyGraph()
    graph.add_resource_node(
        ResourceNode(
            address="aws_instance.app",
            resource_type="aws_instance",
            resource_name="app",
        )
    )

    # Reference to an external VPC not present in the plan
    graph.add_dependency_edge(
        DependencyEdge(
            source="aws_instance.app",
            target="aws_vpc.external_vpc",
            evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
            provenance="config.vpc_id",
        )
    )

    analysis = graph.analyze()
    assert "aws_vpc.external_vpc" in analysis.missing_dependencies

    # Target node was created with appropriate missing metadata
    target_node = graph.get_resource_node("aws_vpc.external_vpc")
    assert target_node is not None
    assert target_node.is_in_plan is False
    assert target_node.metadata.get("missing_from_plan") is True


def test_no_hallucinated_dependencies():
    """Verify that similar resource names never cause hallucinated dependency edges."""
    graph = DependencyGraph()
    similar_names = [
        "aws_db_instance.customer_prod",
        "aws_db_instance.customer_prod_replica",
        "aws_s3_bucket.customer_prod_data",
        "aws_security_group.customer_prod_sg",
    ]

    for addr in similar_names:
        graph.add_resource_node(
            ResourceNode(
                address=addr,
                resource_type=addr.split(".")[0],
                resource_name=addr.split(".")[1],
            )
        )

    analysis = graph.analyze()
    assert analysis.total_nodes == 4
    assert analysis.total_edges == 0
    assert len(analysis.isolated_nodes) == 4

    # Confirm no edges were guessed
    for addr in similar_names:
        assert graph.get_direct_dependencies(addr) == []
        assert graph.get_direct_dependents(addr) == []


def test_graph_from_plan_with_dependents():
    """Verify full graph construction from delete_with_dependents fixture."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    graph = DependencyGraph.from_parsed_plan(plan)
    analysis = graph.analyze()

    assert analysis.total_nodes == 3
    assert analysis.total_edges == 2
    assert analysis.edges_by_evidence == {EvidenceCategory.TERRAFORM_REFERENCE.value: 2}

    # Primary database has two direct dependents
    db_dependents = graph.get_direct_dependents("aws_db_instance.primary")
    assert sorted(db_dependents) == ["aws_ecs_service.api", "aws_route53_record.db"]
