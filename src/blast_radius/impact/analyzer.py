"""Module D: Impact analysis and blast radius engine."""

import logging

from blast_radius.graph.builder import DependencyGraph
from blast_radius.models.graph import ConfidenceLevel, EvidenceCategory
from blast_radius.models.impact import (
    ImpactAnalysisReport,
    ImpactedResource,
    ImpactType,
    ResourceBlastRadius,
)
from blast_radius.models.plan import NormalizedAction, ParsedPlan, ResourceChange

logger = logging.getLogger("blast_radius.impact")


class ImpactAnalyzer:
    """Analyzes infrastructure changes to estimate blast radius and downstream impact."""

    def __init__(self, graph: DependencyGraph):
        self.graph = graph

    def analyze_plan(self, plan: ParsedPlan) -> ImpactAnalysisReport:
        """Execute comprehensive impact analysis across all planned resource changes."""
        graph_analysis = self.graph.analyze()
        missing_warnings: list[str] = []

        if graph_analysis.missing_dependencies:
            for missing_target in graph_analysis.missing_dependencies:
                missing_warnings.append(
                    f"Plan references '{missing_target}' which is not defined in resource_changes. "
                    "Downstream impact analysis for this dependency may be incomplete."
                )

        if graph_analysis.cycles:
            for cycle in graph_analysis.cycles:
                missing_warnings.append(
                    f"Dependency cycle detected ({cycle.description}). Circular reachability "
                    "analyzed safely without recursion."
                )

        # Analyze blast radius for each changing resource
        resource_radii: list[ResourceBlastRadius] = []
        all_impacted_addresses: set[str] = set()
        direct_impact_count = 0
        transitive_impact_count = 0
        has_destructive_impact = False

        for change in plan.resource_changes:
            # Skip no-op and read operations
            if change.normalized_action in {NormalizedAction.NO_OP, NormalizedAction.READ}:
                continue

            radius = self.analyze_resource_change(change)
            resource_radii.append(radius)

            if radius.is_destructive and radius.total_impacted_count > 0:
                has_destructive_impact = True

            for impacted in radius.impacted_resources:
                all_impacted_addresses.add(impacted.address)
                if impacted.impact_type == ImpactType.DIRECT:
                    direct_impact_count += 1
                else:
                    transitive_impact_count += 1

        total_nodes = self.graph.raw_graph.number_of_nodes()
        unaffected_count = max(0, total_nodes - len(all_impacted_addresses) - len(resource_radii))

        return ImpactAnalysisReport(
            total_changed_resources=len(resource_radii),
            total_impacted_resources=len(all_impacted_addresses),
            direct_impact_count=direct_impact_count,
            transitive_impact_count=transitive_impact_count,
            unaffected_resource_count=unaffected_count,
            resource_blast_radii=resource_radii,
            unique_impacted_addresses=sorted(all_impacted_addresses),
            missing_information_warnings=missing_warnings,
            has_destructive_impact=has_destructive_impact
            or any(r.is_destructive for r in resource_radii),
            metadata={
                "terraform_version": plan.terraform_version,
                "format_version": plan.format_version,
            },
        )

    def analyze_resource_change(self, change: ResourceChange) -> ResourceBlastRadius:
        """Calculate blast radius and downstream dependencies for a single resource change."""
        address = change.address
        action = change.normalized_action
        is_destructive = change.is_destructive

        # New resource additions have zero prior downstream dependents
        if action == NormalizedAction.CREATE:
            return ResourceBlastRadius(
                resource_address=address,
                action=action,
                is_destructive=is_destructive,
                direct_dependents_count=0,
                transitive_dependents_count=0,
                total_impacted_count=0,
                impacted_resources=[],
                missing_evidence_warnings=[],
                summary=(
                    f"Resource '{address}' is a new addition (create); "
                    "no existing downstream dependents."
                ),
            )

        # Retrieve direct and transitive dependents
        direct_dependents = set(self.graph.get_direct_dependents(address))
        all_dependents = self.graph.get_transitive_dependents(address)
        transitive_dependents = all_dependents - direct_dependents

        impacted_items: list[ImpactedResource] = []
        missing_evidence_warnings: list[str] = []

        # Process direct dependents
        for dep_addr in sorted(direct_dependents):
            impacted = self._build_impacted_resource(
                dependent_address=dep_addr,
                triggering_change=change,
                impact_type=ImpactType.DIRECT,
            )
            impacted_items.append(impacted)
            if impacted.has_missing_evidence:
                missing_evidence_warnings.append(
                    f"Direct dependent '{dep_addr}' contains incomplete evidence."
                )

        # Process transitive dependents
        for dep_addr in sorted(transitive_dependents):
            impacted = self._build_impacted_resource(
                dependent_address=dep_addr,
                triggering_change=change,
                impact_type=ImpactType.TRANSITIVE,
            )
            impacted_items.append(impacted)
            if impacted.has_missing_evidence:
                missing_evidence_warnings.append(
                    f"Transitive dependent '{dep_addr}' contains incomplete evidence."
                )

        total_impacted = len(impacted_items)
        if total_impacted == 0:
            summary = (
                f"Resource '{address}' ({action.value}) has 0 known downstream dependents. "
                "Blast radius is isolated."
            )
        else:
            summary = (
                f"Resource '{address}' ({action.value}) impacts {len(direct_dependents)} direct "
                f"and {len(transitive_dependents)} transitive downstream resources."
            )

        return ResourceBlastRadius(
            resource_address=address,
            action=action,
            is_destructive=is_destructive,
            direct_dependents_count=len(direct_dependents),
            transitive_dependents_count=len(transitive_dependents),
            total_impacted_count=total_impacted,
            impacted_resources=impacted_items,
            missing_evidence_warnings=missing_evidence_warnings,
            summary=summary,
        )

    def _build_impacted_resource(
        self,
        dependent_address: str,
        triggering_change: ResourceChange,
        impact_type: ImpactType,
    ) -> ImpactedResource:
        """Construct detailed ImpactedResource with provenance and explanation."""
        node = self.graph.get_resource_node(dependent_address)
        res_type = node.resource_type if node else dependent_address.split(".")[0]

        # Find shortest path from dependent to triggering change: dependent -> ... -> triggering
        paths = self.graph.get_impact_paths(dependent_address, triggering_change.address)
        shortest_path = paths[0] if paths else [dependent_address, triggering_change.address]
        path_length = max(1, len(shortest_path) - 1)

        # Gather evidence along the path
        evidence: list[str] = []
        has_missing = False
        raw_g = self.graph.raw_graph

        for i in range(len(shortest_path) - 1):
            u, v = shortest_path[i], shortest_path[i + 1]
            if raw_g.has_edge(u, v):
                edge_data = raw_g[u][v]
                provenance = edge_data.get("provenance", "unknown")
                evidence.append(f"{u} -> {v} via {provenance}")
                if edge_data.get("evidence_category") == EvidenceCategory.UNKNOWN.value:
                    has_missing = True
            else:
                has_missing = True

        # Generate human-readable explanation
        action_val = triggering_change.normalized_action.value
        if impact_type == ImpactType.DIRECT:
            explanation = (
                f"Direct dependent: '{dependent_address}' explicitly depends on "
                f"'{triggering_change.address}', which is slated for {action_val}."
            )
        else:
            path_str = " -> ".join(shortest_path)
            explanation = (
                f"Transitive dependent: '{dependent_address}' depends on "
                f"'{triggering_change.address}' via dependency chain ({path_str})."
            )

        # Potential failure scenario deduction
        scenario = self._deduce_failure_scenario(
            triggering_type=triggering_change.resource_type,
            triggering_action=triggering_change.normalized_action,
        )

        return ImpactedResource(
            address=dependent_address,
            resource_type=res_type,
            impact_type=impact_type,
            triggering_resource=triggering_change.address,
            triggering_action=triggering_change.normalized_action,
            shortest_path=shortest_path,
            path_length=path_length,
            evidence=evidence,
            explanation=explanation,
            potential_failure_scenario=scenario,
            confidence=ConfidenceLevel.VERIFIED if not has_missing else ConfidenceLevel.MEDIUM,
            has_missing_evidence=has_missing,
        )

    @staticmethod
    def _deduce_failure_scenario(
        triggering_type: str,
        triggering_action: NormalizedAction,
    ) -> str:
        """Deduce contextual failure scenario based on resource domain and action."""
        action_verb = (
            "Destruction" if triggering_action == NormalizedAction.DELETE else "Modification"
        )
        if triggering_action == NormalizedAction.REPLACE:
            action_verb = "Replacement and transient recreation"

        lower_type = triggering_type.lower()
        if any(db in lower_type for db in ["db", "rds", "dynamo", "database", "elasticache"]):
            return (
                f"{action_verb} of database tier may cause connection pool exhaustion, "
                "query timeout failures, or dependent service startup crashes."
            )
        if any(net in lower_type for net in ["subnet", "vpc", "route", "gateway", "nat"]):
            return (
                f"{action_verb} of network infrastructure may trigger packet blackholing, "
                "subnet isolation, or unreachable service endpoints."
            )
        if any(sec in lower_type for sec in ["security_group", "iam", "policy", "role"]):
            return (
                f"{action_verb} of security or authorization controls may lead to "
                "permission denial, rejected ingress traffic, or dropped API calls."
            )
        if any(stg in lower_type for stg in ["s3", "efs", "ebs", "volume"]):
            return (
                f"{action_verb} of persistent storage may result in read/write I/O errors, "
                "missing static assets, or data access failure."
            )
        return (
            f"{action_verb} of upstream dependency establishes potential downstream "
            "operational disruption or degraded service functionality."
        )
