"""Pydantic models for infrastructure impact analysis and blast radius calculation."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from blast_radius.models.graph import ConfidenceLevel
from blast_radius.models.plan import NormalizedAction


class ImpactType(StrEnum):
    """Classification of impact relationship."""

    DIRECT = "direct"
    TRANSITIVE = "transitive"


class ImpactedResource(BaseModel):
    """Details of a single resource impacted by an upstream change."""

    address: str = Field(..., description="Canonical address of impacted resource")
    resource_type: str = Field(..., description="Resource type of impacted resource")
    impact_type: ImpactType = Field(..., description="Direct or transitive impact")
    triggering_resource: str = Field(
        ..., description="Resource undergoing change that caused this impact"
    )
    triggering_action: NormalizedAction = Field(
        ..., description="Action proposed on triggering resource"
    )
    shortest_path: list[str] = Field(
        default_factory=list,
        description="Dependency path from impacted resource to triggering resource",
    )
    path_length: int = Field(
        1, description="Number of dependency hops (1 for direct, >1 for transitive)"
    )
    evidence: list[str] = Field(
        default_factory=list, description="Provenance strings along the dependency path"
    )
    explanation: str = Field(
        ..., description="Evidence-backed explanation of why this resource is impacted"
    )
    potential_failure_scenario: str = Field(
        ..., description="Description of potential disruption or failure mode"
    )
    confidence: ConfidenceLevel = Field(
        ConfidenceLevel.VERIFIED, description="Confidence level of this impact assessment"
    )
    has_missing_evidence: bool = Field(
        False, description="Whether any link in the dependency chain lacks complete evidence"
    )


class ResourceBlastRadius(BaseModel):
    """Blast radius scope and downstream impact for a single resource change."""

    resource_address: str = Field(..., description="Address of resource undergoing change")
    action: NormalizedAction = Field(..., description="Proposed lifecycle action")
    is_destructive: bool = Field(..., description="Whether action is destructive (delete/replace)")
    direct_dependents_count: int = Field(0, description="Count of immediate dependents")
    transitive_dependents_count: int = Field(
        0, description="Count of downstream transitive dependents"
    )
    total_impacted_count: int = Field(0, description="Total unique downstream resources impacted")
    impacted_resources: list[ImpactedResource] = Field(
        default_factory=list, description="List of all downstream impacted resources"
    )
    missing_evidence_warnings: list[str] = Field(
        default_factory=list, description="Warnings regarding incomplete dependency information"
    )
    summary: str = Field(..., description="Human-readable summary of blast radius scope")


class ImpactAnalysisReport(BaseModel):
    """Complete impact analysis report spanning all proposed changes in a plan."""

    total_changed_resources: int = Field(0, description="Total resources with proposed changes")
    total_impacted_resources: int = Field(
        0, description="Unique count of all downstream resources impacted across plan"
    )
    direct_impact_count: int = Field(0, description="Total direct impact relationships")
    transitive_impact_count: int = Field(0, description="Total transitive impact relationships")
    unaffected_resource_count: int = Field(
        0, description="Resources in graph with no proposed changes and no downstream impact"
    )
    resource_blast_radii: list[ResourceBlastRadius] = Field(
        default_factory=list, description="Blast radius analysis per changed resource"
    )
    unique_impacted_addresses: list[str] = Field(
        default_factory=list, description="List of all unique addresses impacted"
    )
    missing_information_warnings: list[str] = Field(
        default_factory=list, description="System-wide missing dependency warnings"
    )
    has_destructive_impact: bool = Field(
        False, description="Whether any destructive change impacts downstream resources"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Execution metadata")
