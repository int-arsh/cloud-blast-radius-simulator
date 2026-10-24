"""Pydantic data models for parsed and normalized Terraform plans."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NormalizedAction(StrEnum):
    """Normalized infrastructure lifecycle action."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    REPLACE = "replace"
    NO_OP = "no-op"
    READ = "read"
    UNSUPPORTED = "unsupported"


def normalize_actions(actions: list[str]) -> NormalizedAction:
    """Map raw Terraform plan action list to a normalized lifecycle action."""
    action_set = set(actions)
    if action_set == {"create"}:
        return NormalizedAction.CREATE
    if action_set == {"update"}:
        return NormalizedAction.UPDATE
    if action_set == {"delete"}:
        return NormalizedAction.DELETE
    if action_set == {"delete", "create"}:
        return NormalizedAction.REPLACE
    if action_set == {"no-op"}:
        return NormalizedAction.NO_OP
    if action_set == {"read"}:
        return NormalizedAction.READ
    return NormalizedAction.UNSUPPORTED


class ResourceChange(BaseModel):
    """Normalized representation of a single resource change in a Terraform plan."""

    address: str = Field(..., description="Full resource address e.g. aws_db_instance.primary")
    resource_type: str = Field(..., description="Resource type e.g. aws_db_instance")
    resource_name: str = Field(..., description="Resource name e.g. primary")
    module_address: str | None = Field(None, description="Module path if defined")
    mode: str = Field("managed", description="Terraform mode: managed or data")
    provider_name: str | None = Field(None, description="Terraform provider identifier")
    raw_actions: list[str] = Field(default_factory=list, description="Raw action list from plan")
    normalized_action: NormalizedAction = Field(..., description="Normalized lifecycle action")
    is_destructive: bool = Field(False, description="Whether this change destroys existing state")
    replace_paths: list[str] = Field(
        default_factory=list, description="Attributes forcing replacement"
    )
    before_attributes: dict[str, Any] = Field(
        default_factory=dict, description="Redacted before attributes"
    )
    after_attributes: dict[str, Any] = Field(
        default_factory=dict, description="Redacted after attributes"
    )
    declared_dependencies: list[str] = Field(
        default_factory=list, description="Explicit dependencies extracted from plan configuration"
    )

    @classmethod
    def from_raw_change(
        cls,
        raw_change: dict[str, Any],
        config_deps: list[str] | None = None,
        redacted_before: dict[str, Any] | None = None,
        redacted_after: dict[str, Any] | None = None,
    ) -> "ResourceChange":
        """Construct a normalized ResourceChange from raw Terraform plan entry."""
        address = raw_change.get("address", "unknown.resource")
        res_type = raw_change.get("type", address.split(".")[0] if "." in address else "unknown")
        res_name = raw_change.get("name", address.split(".")[-1] if "." in address else "unknown")
        module_address = raw_change.get("module_address")
        mode = raw_change.get("mode", "managed")
        provider_name = raw_change.get("provider_name")

        change_obj = raw_change.get("change", {})
        raw_actions = change_obj.get("actions", [])
        normalized = normalize_actions(raw_actions)
        is_destructive = normalized in {NormalizedAction.DELETE, NormalizedAction.REPLACE}

        replace_paths_raw = change_obj.get("replace_paths", [])
        # replace_paths can be list of lists/strings
        replace_paths = [
            ".".join(str(p) for p in path) if isinstance(path, list) else str(path)
            for path in replace_paths_raw
        ]

        return cls(
            address=address,
            resource_type=res_type,
            resource_name=res_name,
            module_address=module_address,
            mode=mode,
            provider_name=provider_name,
            raw_actions=raw_actions,
            normalized_action=normalized,
            is_destructive=is_destructive,
            replace_paths=replace_paths,
            before_attributes=redacted_before or {},
            after_attributes=redacted_after or {},
            declared_dependencies=config_deps or [],
        )


class ParsedPlan(BaseModel):
    """Complete parsed and normalized Terraform plan."""

    format_version: str = Field(..., description="Terraform plan format version")
    terraform_version: str | None = Field(
        None, description="Terraform CLI version that generated the plan"
    )
    raw_resource_count: int = Field(0, description="Total resource changes present in plan")
    resource_changes: list[ResourceChange] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    is_valid: bool = Field(True, description="Whether plan was parsed and validated successfully")

    @property
    def destructive_changes(self) -> list[ResourceChange]:
        """Return list of changes that destroy existing infrastructure."""
        return [rc for rc in self.resource_changes if rc.is_destructive]
