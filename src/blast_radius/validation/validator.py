"""Module A: Input and validation for Terraform plan JSON."""

import json
from typing import Any

from pydantic import BaseModel, Field

from blast_radius.config import get_settings


class PlanValidationResult(BaseModel):
    """Result of plan input validation."""

    is_valid: bool = Field(..., description="Whether plan is structurally valid for parsing")
    errors: list[str] = Field(default_factory=list, description="Validation failure reasons")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal structural warnings")
    format_version: str | None = Field(None, description="Extracted plan format version")
    terraform_version: str | None = Field(None, description="Extracted Terraform version")
    size_bytes: int = Field(0, description="Size of input payload in bytes")
    data: dict[str, Any] | None = Field(None, description="Parsed plan dictionary if valid")


class PlanValidator:
    """Validates raw Terraform plan input against structural and safety requirements."""

    SUPPORTED_MAJOR_VERSIONS = {"0", "1"}

    def __init__(self, max_size_bytes: int | None = None):
        settings = get_settings()
        self.max_size_bytes = max_size_bytes or settings.max_plan_size_bytes

    def validate_raw(self, content: bytes | str) -> PlanValidationResult:
        """Validate raw bytes or string payload."""
        size_bytes = len(content.encode("utf-8") if isinstance(content, str) else content)

        if size_bytes > self.max_size_bytes:
            return PlanValidationResult(
                is_valid=False,
                errors=[
                    f"Plan size ({size_bytes} bytes) exceeds configured limit of "
                    f"{self.max_size_bytes} bytes."
                ],
                size_bytes=size_bytes,
            )

        if size_bytes == 0:
            return PlanValidationResult(
                is_valid=False,
                errors=["Plan content is empty."],
                size_bytes=0,
            )

        try:
            raw_text = content.decode("utf-8") if isinstance(content, bytes) else content
            parsed_data = json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return PlanValidationResult(
                is_valid=False,
                errors=[f"Malformed JSON: {exc}"],
                size_bytes=size_bytes,
            )

        return self.validate_dict(parsed_data, size_bytes=size_bytes)

    def validate_dict(self, data: Any, size_bytes: int = 0) -> PlanValidationResult:
        """Validate pre-parsed JSON dictionary structure."""
        if not isinstance(data, dict):
            return PlanValidationResult(
                is_valid=False,
                errors=[
                    "Expected top-level JSON object (dictionary), received " + type(data).__name__
                ],
                size_bytes=size_bytes,
            )

        errors: list[str] = []
        warnings: list[str] = []

        format_version = data.get("format_version")
        if format_version is None:
            errors.append("Missing required field 'format_version' in Terraform plan JSON.")
        elif not isinstance(format_version, str):
            errors.append(
                f"'format_version' must be a string, got {type(format_version).__name__}."
            )
        else:
            major_ver = format_version.split(".")[0]
            if major_ver not in self.SUPPORTED_MAJOR_VERSIONS:
                warnings.append(
                    f"Plan format version '{format_version}' is outside verified range "
                    f"(supported major versions: {sorted(self.SUPPORTED_MAJOR_VERSIONS)})."
                )

        terraform_version = data.get("terraform_version")
        if terraform_version is not None and not isinstance(terraform_version, str):
            warnings.append(
                f"'terraform_version' is not a string: {type(terraform_version).__name__}."
            )

        resource_changes = data.get("resource_changes")
        if resource_changes is None:
            # Check if this is an empty plan (no changes planned)
            if "planned_values" in data or "prior_state" in data:
                warnings.append("Plan contains no 'resource_changes' key. No changes detected.")
            else:
                errors.append("Missing 'resource_changes' block in Terraform plan JSON.")
        elif not isinstance(resource_changes, list):
            actual_type = type(resource_changes).__name__
            errors.append(f"'resource_changes' must be an array of objects, got {actual_type}.")

        is_valid = len(errors) == 0
        return PlanValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            format_version=str(format_version) if format_version else None,
            terraform_version=str(terraform_version) if terraform_version else None,
            size_bytes=size_bytes,
            data=data if is_valid else None,
        )
