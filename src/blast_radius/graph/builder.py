"""Module C: Infrastructure dependency graph engine using NetworkX."""

import logging
from collections import Counter

import networkx as nx

from blast_radius.models.graph import (
    ConfidenceLevel,
    CycleInfo,
    DependencyEdge,
    EvidenceCategory,
    GraphAnalysisResult,
    ResourceNode,
)
from blast_radius.models.plan import ParsedPlan

logger = logging.getLogger("blast_radius.graph")


class DependencyGraph:
    """Directed graph representing cloud infrastructure dependencies.

    Edge Convention:
        (u, v) representing `u -> v` signifies that `u` depends on `v`.
        Example: `Application -> Database`.
        Therefore:
        - `G.successors(u)` yields the direct dependencies of `u`.
        - `G.predecessors(v)` yields the direct dependents of `v` (impacted if `v` changes).
        - `nx.ancestors(G, v)` yields all transitive dependents affected if `v` changes.
    """

    def __init__(self):
        self._graph: nx.DiGraph = nx.DiGraph()
        self._missing_dependencies: set[str] = set()

    @property
    def raw_graph(self) -> nx.DiGraph:
        """Access underlying NetworkX DiGraph."""
        return self._graph

    def add_resource_node(self, node: ResourceNode) -> None:
        """Add or update a resource node in the graph."""
        self._graph.add_node(node.address, data=node)

    def get_resource_node(self, address: str) -> ResourceNode | None:
        """Retrieve ResourceNode metadata by address."""
        node_entry = self._graph.nodes.get(address)
        if node_entry and "data" in node_entry:
            return node_entry["data"]
        return None

    def add_dependency_edge(self, edge: DependencyEdge) -> None:
        """Add a directed dependency edge: source depends on target."""
        # Ensure source node exists
        if edge.source not in self._graph:
            s_type = edge.source.split(".")[0] if "." in edge.source else "unknown"
            s_name = edge.source.split(".")[-1] if "." in edge.source else "unknown"
            self.add_resource_node(
                ResourceNode(
                    address=edge.source,
                    resource_type=s_type,
                    resource_name=s_name,
                    is_in_plan=False,
                    metadata={"implicit_node": True},
                )
            )

        # Ensure target node exists
        if edge.target not in self._graph:
            t_type = edge.target.split(".")[0] if "." in edge.target else "unknown"
            t_name = edge.target.split(".")[-1] if "." in edge.target else "unknown"
            self.add_resource_node(
                ResourceNode(
                    address=edge.target,
                    resource_type=t_type,
                    resource_name=t_name,
                    is_in_plan=False,
                    metadata={"missing_from_plan": True},
                )
            )
            self._missing_dependencies.add(edge.target)

        self._graph.add_edge(
            edge.source,
            edge.target,
            data=edge,
            evidence_category=edge.evidence_category.value,
            confidence=edge.confidence.value,
            provenance=edge.provenance,
        )

    def get_direct_dependencies(self, address: str) -> list[str]:
        """Return resources that the given resource directly depends upon."""
        if address not in self._graph:
            return []
        return sorted(self._graph.successors(address))

    def get_direct_dependents(self, address: str) -> list[str]:
        """Return resources that directly depend upon the given resource."""
        if address not in self._graph:
            return []
        return sorted(self._graph.predecessors(address))

    def get_transitive_dependents(self, address: str) -> set[str]:
        """Return all downstream resources affected if the given resource is changed/destroyed."""
        if address not in self._graph:
            return set()
        return nx.ancestors(self._graph, address)

    def get_transitive_dependencies(self, address: str) -> set[str]:
        """Return all upstream resources that the given resource depends on transitively."""
        if address not in self._graph:
            return set()
        return nx.descendants(self._graph, address)

    def get_impact_paths(self, dependent: str, target: str) -> list[list[str]]:
        """Return all simple paths showing how dependent resource depends on target."""
        if dependent not in self._graph or target not in self._graph:
            return []
        try:
            return list(nx.all_simple_paths(self._graph, source=dependent, target=target))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def detect_cycles(self) -> list[CycleInfo]:
        """Detect directed cycles without infinite recursion."""
        cycles: list[CycleInfo] = []
        try:
            raw_cycles = list(nx.simple_cycles(self._graph))
            for idx, cycle in enumerate(raw_cycles):
                cycle_nodes = list(cycle)
                # Close the loop for display clarity
                display_loop = " -> ".join(cycle_nodes + [cycle_nodes[0]])
                cycles.append(
                    CycleInfo(
                        cycle_id=f"cycle-{idx + 1}",
                        nodes=cycle_nodes,
                        description=f"Circular dependency detected: {display_loop}",
                    )
                )
        except Exception as exc:
            logger.error(f"Error while analyzing graph cycles: {exc}", exc_info=True)
        return cycles

    def analyze(self) -> GraphAnalysisResult:
        """Perform topological analysis on the dependency graph."""
        total_nodes = self._graph.number_of_nodes()
        total_edges = self._graph.number_of_edges()

        # Breakdown of edges by evidence
        evidence_counts: Counter[str] = Counter()
        for _, _, data in self._graph.edges(data=True):
            cat = data.get("evidence_category", EvidenceCategory.UNKNOWN.value)
            evidence_counts[cat] += 1

        # Detect isolated nodes (0 in-degree and 0 out-degree)
        isolated = [
            node
            for node in self._graph.nodes()
            if self._graph.in_degree(node) == 0 and self._graph.out_degree(node) == 0
        ]

        cycles = self.detect_cycles()

        return GraphAnalysisResult(
            total_nodes=total_nodes,
            total_edges=total_edges,
            edges_by_evidence=dict(evidence_counts),
            cycles=cycles,
            isolated_nodes=sorted(isolated),
            missing_dependencies=sorted(self._missing_dependencies),
        )

    @classmethod
    def from_parsed_plan(
        cls,
        parsed_plan: ParsedPlan,
        external_edges: list[DependencyEdge] | None = None,
    ) -> "DependencyGraph":
        """Construct DependencyGraph from a ParsedPlan with strict provenance."""
        graph = cls()

        # 1. Register all resource changes as nodes
        for rc in parsed_plan.resource_changes:
            node = ResourceNode(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_name=rc.resource_name,
                mode=rc.mode,
                provider_name=rc.provider_name,
                is_in_plan=True,
                action=rc.normalized_action,
                is_destructive=rc.is_destructive,
                metadata={
                    "replace_paths": rc.replace_paths,
                    "raw_actions": rc.raw_actions,
                },
            )
            graph.add_resource_node(node)

        # 2. Add edges from verified declared configuration dependencies
        for rc in parsed_plan.resource_changes:
            for dep_target in rc.declared_dependencies:
                edge = DependencyEdge(
                    source=rc.address,
                    target=dep_target,
                    evidence_category=EvidenceCategory.TERRAFORM_REFERENCE,
                    confidence=ConfidenceLevel.VERIFIED,
                    provenance=f"configuration.root_module[{rc.address}].references({dep_target})",
                    is_direct=True,
                )
                graph.add_dependency_edge(edge)

        # 3. Add any verified external edges (e.g. from runtime observations or explicit fixtures)
        if external_edges:
            for ext_edge in external_edges:
                graph.add_dependency_edge(ext_edge)

        return graph
