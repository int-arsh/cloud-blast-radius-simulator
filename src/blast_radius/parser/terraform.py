"""Module B: Terraform plan parser and change normalizer."""

import logging
from collections import Counter
from typing import Any

from blast_radius.logging import redact_data
from blast_radius.models.plan import (
    NormalizedAction,
    ParsedPlan,
    ResourceChange,
)
from blast_radius.validation.validator import PlanValidator

logger = logging.getLogger("blast_radius.parser")


class TerraformPlanParser:
    """Parses and normalizes Terraform plan JSON documents into structured domain models."""

    def __init__(self, validator: PlanValidator | None = None):
        self.validator = validator or PlanValidator()

    def parse_raw(self, content: bytes | str) -> ParsedPlan:
        """Validate and parse raw bytes or string into a ParsedPlan."""
        validation = self.validator.validate_raw(content)
        if not validation.is_valid or validation.data is None:
            return ParsedPlan(
                format_version=validation.format_version or "unknown",
                terraform_version=validation.terraform_version,
                raw_resource_count=0,
                resource_changes=[],
                action_counts={},
                warnings=validation.errors + validation.warnings,
                is_valid=False,
            )

        return self.parse_dict(validation.data, initial_warnings=validation.warnings)

    def parse_dict(
        self,
        data: dict[str, Any],
        initial_warnings: list[str] | None = None,
    ) -> ParsedPlan:
        """Parse validated dictionary into ParsedPlan."""
        warnings: list[str] = list(initial_warnings or [])
        format_version = str(data.get("format_version", "unknown"))
        terraform_version = data.get("terraform_version")

        # 1. Extract explicit dependencies from configuration block if present
        config_dependencies = self._extract_config_dependencies(data.get("configuration", {}))

        # 2. Extract resource changes
        raw_changes = data.get("resource_changes", [])
        if not isinstance(raw_changes, list):
            raw_changes = []

        parsed_changes: list[ResourceChange] = []
        action_counter: Counter[str] = Counter()

        for idx, change_item in enumerate(raw_changes):
            if not isinstance(change_item, dict):
                warnings.append(f"resource_changes[{idx}] is not an object; skipped.")
                continue

            address = change_item.get("address")
            if not address:
                warnings.append(f"resource_changes[{idx}] is missing 'address'; skipped.")
                continue

            change_data = change_item.get("change", {})
            if not isinstance(change_data, dict):
                warnings.append(f"Resource '{address}' has malformed 'change' block.")
                change_data = {}

            # Redact sensitive attributes in before/after snapshots
            raw_before = change_data.get("before") or {}
            raw_after = change_data.get("after") or {}
            redacted_before = redact_data(raw_before) if isinstance(raw_before, dict) else {}
            redacted_after = redact_data(raw_after) if isinstance(raw_after, dict) else {}

            # Retrieve declared dependencies for this address
            deps = config_dependencies.get(address, [])

            rc = ResourceChange.from_raw_change(
                raw_change=change_item,
                config_deps=deps,
                redacted_before=redacted_before,
                redacted_after=redacted_after,
            )

            if rc.normalized_action == NormalizedAction.UNSUPPORTED:
                warnings.append(
                    f"Resource '{address}' has unsupported action combination: {rc.raw_actions}."
                )

            action_counter[rc.normalized_action.value] += 1
            parsed_changes.append(rc)

        return ParsedPlan(
            format_version=format_version,
            terraform_version=str(terraform_version) if terraform_version else None,
            raw_resource_count=len(parsed_changes),
            resource_changes=parsed_changes,
            action_counts=dict(action_counter),
            warnings=warnings,
            is_valid=True,
        )

    def _extract_config_dependencies(self, config_block: dict[str, Any]) -> dict[str, list[str]]:
        """Extract declared dependencies (depends_on and expressions) from configuration."""
        declared_deps: dict[str, set[str]] = {}

        if not isinstance(config_block, dict):
            return {}

        root_module = config_block.get("root_module", {})
        if not isinstance(root_module, dict):
            return {}

        self._collect_module_dependencies(root_module, declared_deps)
        return {addr: sorted(deps) for addr, deps in declared_deps.items()}

    def _collect_module_dependencies(
        self,
        module_block: dict[str, Any],
        deps_acc: dict[str, set[str]],
    ) -> None:
        """Recursively inspect module resources and module_calls for references."""
        resources = module_block.get("resources", [])
        if isinstance(resources, list):
            for res in resources:
                if not isinstance(res, dict):
                    continue
                address = res.get("address")
                if not address:
                    continue

                if address not in deps_acc:
                    deps_acc[address] = set()

                # Explicit depends_on
                for dep in res.get("depends_on", []):
                    if isinstance(dep, str):
                        deps_acc[address].add(dep)

                # Reference expressions
                expressions = res.get("expressions", {})
                if isinstance(expressions, dict):
                    for expr in expressions.values():
                        if isinstance(expr, dict):
                            for ref in expr.get("references", []):
                                if isinstance(ref, str):
                                    resolved = self._normalize_reference_target(ref)
                                    if resolved and resolved != address:
                                        deps_acc[address].add(resolved)

        # Inspect nested module calls
        module_calls = module_block.get("module_calls", {})
        if isinstance(module_calls, dict):
            for mod in module_calls.values():
                if isinstance(mod, dict) and "module" in mod:
                    self._collect_module_dependencies(mod["module"], deps_acc)

    @staticmethod
    def _normalize_reference_target(ref: str) -> str | None:
        """Resolve a reference string (e.g., 'aws_db_instance.primary.id') to resource address."""
        # Ignore variables, local values, path, etc.
        if ref.startswith(("var.", "local.", "path.", "count.", "each.")):
            return None

        parts = ref.split(".")
        if len(parts) >= 2:
            # E.g. "aws_db_instance.primary.id" -> "aws_db_instance.primary"
            # E.g. "data.aws_ami.ubuntu.id" -> "data.aws_ami.ubuntu"
            if parts[0] == "data" and len(parts) >= 3:
                return f"{parts[0]}.{parts[1]}.{parts[2]}"
            return f"{parts[0]}.{parts[1]}"
        return None
