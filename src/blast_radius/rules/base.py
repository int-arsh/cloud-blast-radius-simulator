"""Base class for deterministic risk rules."""

from abc import ABC, abstractmethod

from blast_radius.graph.builder import DependencyGraph
from blast_radius.models.impact import ImpactAnalysisReport
from blast_radius.models.plan import ParsedPlan
from blast_radius.models.risk import RiskFinding


class BaseRiskRule(ABC):
    """Abstract base class for all deterministic infrastructure safety rules."""

    rule_id: str
    name: str
    description: str

    @abstractmethod
    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        """Evaluate plan, graph, and impact report against this deterministic rule."""
        raise NotImplementedError
