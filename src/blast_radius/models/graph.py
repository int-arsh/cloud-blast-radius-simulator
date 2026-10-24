"""Pydantic data models for the infrastructure dependency graph."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from blast_radius.models.plan import NormalizedAction


class EvidenceCategory(StrEnum):
    """Origin and evidence category of a dependency edge."""

    TERRAFORM_REFERENCE = "terraform_reference"
    EXPLICIT_FIXTURE = "explicit_fixture"
    RUNTIME_OBSERVATION = "runtime_observation"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    """Confidence level of a dependency relationship."""

    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DependencyEdge(BaseModel):
    """Directed dependency edge representing: source depends on target."""

    source: str = Field(..., description="Dependent resource address (the depender)")
    target: str = Field(..., description="Depended-upon resource address (the dependee)")
    evidence_category: EvidenceCategory = Field(
        ..., description="Evidence category backing this relationship"
    )
    confidence: ConfidenceLevel = Field(
        ConfidenceLevel.VERIFIED, description="Confidence level of this relationship"
    )
    provenance: str = Field(
        ..., description="Exact provenance (config field, expression, or fixture id)"
    )
    is_direct: bool = Field(True, description="Whether this represents a direct relationship")


class ResourceNode(BaseModel):
    """Node in the infrastructure dependency graph."""

    address: str = Field(..., description="Canonical resource address")
    resource_type: str = Field(..., description="Resource type e.g. aws_instance")
    resource_name: str = Field(..., description="Resource name e.g. web")
    mode: str = Field("managed", description="Terraform mode: managed or data")
    provider_name: str | None = Field(None, description="Terraform provider")
    is_in_plan: bool = Field(True, description="Whether resource was defined in plan changes")
    action: NormalizedAction | None = Field(
        None, description="Proposed action if resource is in plan"
    )
    is_destructive: bool = Field(False, description="Whether change is destructive")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary node metadata")


class CycleInfo(BaseModel):
    """Information regarding a detected dependency cycle."""

    cycle_id: str = Field(..., description="Unique cycle identifier")
    nodes: list[str] = Field(..., description="Ordered list of addresses forming the cycle")
    description: str = Field(..., description="Human-readable explanation of the cycle")


class GraphAnalysisResult(BaseModel):
    """Summary of graph construction and topology inspection."""

    total_nodes: int = Field(0, description="Total resource nodes in graph")
    total_edges: int = Field(0, description="Total dependency edges in graph")
    edges_by_evidence: dict[str, int] = Field(
        default_factory=dict, description="Edge count breakdown by evidence category"
    )
    cycles: list[CycleInfo] = Field(default_factory=list, description="Detected cycles")
    isolated_nodes: list[str] = Field(
        default_factory=list, description="Nodes with zero in-degree and zero out-degree"
    )
    missing_dependencies: list[str] = Field(
        default_factory=list,
        description="Referenced dependencies that do not exist as known nodes",
    )
