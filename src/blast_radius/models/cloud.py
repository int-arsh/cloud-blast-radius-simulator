"""Pydantic data models for optional live cloud state enrichment."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LiveResourceState(BaseModel):
    """Correlated live cloud state for a resource undergoing change."""

    address: str = Field(..., description="Canonical Terraform resource address")
    resource_type: str = Field(..., description="Terraform resource type (e.g. aws_db_instance)")
    resource_id: str | None = Field(None, description="Cloud provider identifier (e.g. arn or id)")
    exists_in_cloud: bool | None = Field(
        None, description="Whether resource currently exists in target cloud account"
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Live cloud resource tags")
    protection_flags: dict[str, bool] = Field(
        default_factory=dict,
        description="Active safeguard flags (e.g. deletion_protection, termination_protection)",
    )
    live_attributes: dict[str, Any] = Field(
        default_factory=dict, description="Selected verified attributes from live cloud API"
    )
    drift_detected: bool = Field(
        False, description="Whether live cloud attributes diverge from plan 'before' state"
    )
    drift_messages: list[str] = Field(
        default_factory=list, description="Specific attribute drift descriptions"
    )
    is_production_flagged: bool = Field(
        False, description="Whether live tags/attributes confirm production status"
    )
    provenance: str = Field(
        "offline_unauthenticated",
        description="Data provenance (e.g. aws_api, offline_mock, offline_unauthenticated)",
    )


class CloudEnrichmentReport(BaseModel):
    """Consolidated summary of live cloud inspection across a Terraform plan."""

    provider: str = Field("aws", description="Target cloud provider")
    authenticated: bool = Field(False, description="Whether live cloud session was authenticated")
    region: str | None = Field(None, description="Inspected cloud region")
    profile: str | None = Field(None, description="AWS profile used for authentication")
    resources_checked: int = Field(0, description="Total resources evaluated against live state")
    resources_existing: int = Field(0, description="Resources verified as currently existing")
    resources_missing: int = Field(0, description="Resources confirmed absent in cloud")
    drift_count: int = Field(0, description="Count of resources with detected configuration drift")
    protection_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings regarding active protection safeguards on resources being dropped",
    )
    production_violations: list[str] = Field(
        default_factory=list,
        description="Violations where live production tags contradict non-production plans",
    )
    resource_states: dict[str, LiveResourceState] = Field(
        default_factory=dict, description="Mapping of resource address to live state"
    )
