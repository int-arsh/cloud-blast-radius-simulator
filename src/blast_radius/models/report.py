"""Pydantic models for full analysis report exports."""

from typing import Any

from pydantic import BaseModel, Field

from blast_radius.models.cloud import CloudEnrichmentReport
from blast_radius.models.graph import DependencyEdge, ResourceNode
from blast_radius.models.impact import ImpactAnalysisReport
from blast_radius.models.risk import (
    DecisionStatus,
    RiskFinding,
    RiskScoreBreakdown,
)


class FullAnalysisReport(BaseModel):
    """Complete consolidated analysis report for a Terraform plan."""

    analysis_id: str = Field(..., description="Unique analysis run identifier (UUID)")
    timestamp: str = Field(..., description="UTC ISO 8601 timestamp of analysis execution")
    engine_version: str = Field(..., description="Cloud Blast-Radius Simulator version")
    format_version: str = Field(..., description="Terraform plan format version")
    terraform_version: str | None = Field(None, description="Terraform CLI version")
    decision_status: DecisionStatus = Field(..., description="Automated gate status")
    decision_reason: str = Field(..., description="Primary reason justifying the decision status")
    risk_score: float = Field(..., description="Deterministic risk score (0.0 to 100.0)")
    score_breakdown: RiskScoreBreakdown = Field(..., description="Explainable score factors")
    resource_counts: dict[str, int] = Field(
        default_factory=dict, description="Counts of total, changed, and unaffected resources"
    )
    action_counts: dict[str, int] = Field(
        default_factory=dict, description="Counts per normalized lifecycle action"
    )
    dependency_counts: dict[str, int] = Field(
        default_factory=dict, description="Counts of graph nodes, edges, and cycles"
    )
    severity_counts: dict[str, int] = Field(
        default_factory=dict, description="Breakdown of findings by severity level"
    )
    impact_summary: ImpactAnalysisReport = Field(..., description="Downstream impact assessment")
    nodes: list[ResourceNode] = Field(
        default_factory=list, description="Topology graph resource nodes"
    )
    edges: list[DependencyEdge] = Field(
        default_factory=list, description="Topology graph directed dependency edges"
    )
    findings: list[RiskFinding] = Field(
        default_factory=list, description="All detected evidence-backed risk findings"
    )
    warnings: list[str] = Field(default_factory=list, description="System and parser warnings")
    remediations: list[str] = Field(
        default_factory=list, description="Consolidated unique remediation recommendations"
    )
    cloud_enrichment: CloudEnrichmentReport | None = Field(
        None, description="Optional correlated live cloud state and drift report"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Run metadata")
