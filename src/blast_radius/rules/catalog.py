"""Catalog of deterministic infrastructure safety and risk rules."""

from blast_radius.graph.builder import DependencyGraph
from blast_radius.models.graph import ConfidenceLevel
from blast_radius.models.impact import ImpactAnalysisReport
from blast_radius.models.plan import NormalizedAction, ParsedPlan
from blast_radius.models.risk import RiskFinding, RiskSeverity
from blast_radius.rules.base import BaseRiskRule


class RuleCriticalResourceDeletion(BaseRiskRule):
    """RULE-001: Deletion of explicitly designated critical infrastructure."""

    rule_id = "RULE-001"
    name = "Critical Resource Deletion"
    description = "Detects proposed destruction of explicitly designated critical resources."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []
        configured_critical = critical_resources or set()

        for rc in plan.resource_changes:
            if rc.normalized_action != NormalizedAction.DELETE:
                continue

            # Verify explicit criticality
            is_critical = rc.address in configured_critical
            evidence_reasons = []

            if is_critical:
                evidence_reasons.append(
                    f"Resource '{rc.address}' is present in critical_resources configuration."
                )

            # Check explicit tags in before attributes
            tags = rc.before_attributes.get("tags", {})
            if isinstance(tags, dict):
                env = str(tags.get("Environment", "")).lower()
                crit = str(tags.get("Criticality", "")).lower()
                if env == "production" or crit in {"critical", "high"}:
                    is_critical = True
                    evidence_reasons.append(
                        f"Resource tags declare Environment='{env}', Criticality='{crit}'."
                    )

            if is_critical:
                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{rc.address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=RiskSeverity.CRITICAL,
                        resource_address=rc.address,
                        proposed_action=rc.normalized_action,
                        evidence=evidence_reasons,
                        reasoning=(
                            f"Resource '{rc.address}' is designated as critical infrastructure. "
                            "Permanent deletion carries severe operational risk."
                        ),
                        confidence=ConfidenceLevel.VERIFIED,
                        limitations="Criticality is derived from explicit configuration and tags.",
                        remediation=(
                            "Do not delete this resource without change advisory board sign-off."
                        ),
                    )
                )

        return findings


class RuleDestructionWithDependents(BaseRiskRule):
    """RULE-002: Destruction of a resource with known active dependents."""

    rule_id = "RULE-002"
    name = "Destruction of Resource with Known Dependents"
    description = "Detects deletion of resources that other infrastructure components depend upon."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        for radius in impact_report.resource_blast_radii:
            if radius.action == NormalizedAction.DELETE and radius.total_impacted_count > 0:
                direct_count = radius.direct_dependents_count
                total_count = radius.total_impacted_count
                severity = RiskSeverity.CRITICAL if direct_count >= 3 else RiskSeverity.HIGH

                sample_deps = [imp.address for imp in radius.impacted_resources[:3]]
                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{radius.resource_address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=severity,
                        resource_address=radius.resource_address,
                        proposed_action=radius.action,
                        evidence=[
                            f"Downstream dependents count: {direct_count} direct, "
                            f"{total_count} total.",
                            f"Sample impacted resources: {sample_deps}",
                        ],
                        reasoning=(
                            f"Deleting '{radius.resource_address}' will orphan or break "
                            f"{total_count} downstream resources that rely on its availability."
                        ),
                        confidence=ConfidenceLevel.VERIFIED,
                        limitations="Impact reachability is based on verified references.",
                        remediation=(
                            "Decouple or migrate downstream dependent services prior to destroying "
                            f"'{radius.resource_address}'."
                        ),
                    )
                )

        return findings


class RuleResourceReplacementWithDependents(BaseRiskRule):
    """RULE-003: Resource replacement with known downstream dependents."""

    rule_id = "RULE-003"
    name = "Resource Replacement with Known Dependents"
    description = "Detects forced resource replacements that impact downstream dependents."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        for radius in impact_report.resource_blast_radii:
            if radius.action == NormalizedAction.REPLACE and radius.total_impacted_count > 0:
                rc_node = graph.get_resource_node(radius.resource_address)
                replace_paths = rc_node.metadata.get("replace_paths", []) if rc_node else []

                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{radius.resource_address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=RiskSeverity.HIGH,
                        resource_address=radius.resource_address,
                        proposed_action=radius.action,
                        evidence=[
                            f"Attributes forcing replacement: {replace_paths}",
                            f"Impacted dependents count: {radius.total_impacted_count}",
                        ],
                        reasoning=(
                            f"Resource '{radius.resource_address}' will be recreated, "
                            f"disrupting {radius.total_impacted_count} dependent resources."
                        ),
                        confidence=ConfidenceLevel.VERIFIED,
                        limitations="Transient downtime depends on recreation latency.",
                        remediation=(
                            "Configure 'create_before_destroy = true' or use a maintenance window."
                        ),
                    )
                )

        return findings


class RuleMultipleDestructiveActions(BaseRiskRule):
    """RULE-004: Multiple destructive actions in a single plan."""

    rule_id = "RULE-004"
    name = "Multiple Destructive Actions in Single Plan"
    description = "Warns when multiple resources are slated for destruction concurrently."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        destructive = plan.destructive_changes
        if len(destructive) < 2:
            return []

        addresses = [d.address for d in destructive]
        severity = RiskSeverity.HIGH if len(destructive) >= 5 else RiskSeverity.MEDIUM

        return [
            RiskFinding(
                id=f"FINDING-{self.rule_id}-plan",
                rule_id=self.rule_id,
                rule_name=self.name,
                severity=severity,
                resource_address="plan.resource_changes",
                proposed_action=NormalizedAction.DELETE,
                evidence=[
                    f"Total destructive changes in plan: {len(destructive)}",
                    f"Destructive resource list: {addresses}",
                ],
                reasoning=(
                    f"Plan proposes deleting/replacing {len(destructive)} resources concurrently. "
                    "High change concurrency increases the probability of cascading failures."
                ),
                confidence=ConfidenceLevel.VERIFIED,
                limitations="Rule evaluates change concurrency volume, not semantic grouping.",
                remediation=(
                    "Decompose large destructive changes into smaller, isolated pull requests."
                ),
            )
        ]


class RuleProtectionRemoval(BaseRiskRule):
    """RULE-005: Removal of explicitly configured protection."""

    rule_id = "RULE-005"
    name = "Removal of Configured Protection"
    description = "Detects disabling or removal of deletion protection on managed resources."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        for rc in plan.resource_changes:
            if rc.normalized_action != NormalizedAction.UPDATE:
                continue

            before_dp = rc.before_attributes.get("deletion_protection")
            after_dp = rc.after_attributes.get("deletion_protection")

            # Check if deletion protection was disabled
            if before_dp is True and after_dp is False:
                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{rc.address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=RiskSeverity.CRITICAL,
                        resource_address=rc.address,
                        proposed_action=rc.normalized_action,
                        evidence=[f"deletion_protection changed from {before_dp} to {after_dp}."],
                        reasoning=(
                            f"Deletion protection on '{rc.address}' was explicitly disabled. "
                            "This exposes resource to accidental destruction."
                        ),
                        confidence=ConfidenceLevel.VERIFIED,
                        limitations="Inspects explicit 'deletion_protection' attribute change.",
                        remediation=(
                            "Keep deletion protection enabled unless decommissioning is approved."
                        ),
                    )
                )

        return findings


class RuleSensitiveAccessModification(BaseRiskRule):
    """RULE-006: Sensitive access rule modification or wildcard exposure."""

    rule_id = "RULE-006"
    name = "Sensitive Access Modification"
    description = "Detects security group rules opening sensitive access to 0.0.0.0/0."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        for rc in plan.resource_changes:
            if "security_group_rule" not in rc.resource_type:
                continue

            after = rc.after_attributes
            cidr_blocks = after.get("cidr_blocks", [])
            rule_type = after.get("type", "ingress")

            if (
                rule_type == "ingress"
                and isinstance(cidr_blocks, list)
                and "0.0.0.0/0" in cidr_blocks
            ):
                from_port = after.get("from_port", 0)
                to_port = after.get("to_port", 0)
                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{rc.address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=RiskSeverity.HIGH,
                        resource_address=rc.address,
                        proposed_action=rc.normalized_action,
                        evidence=[
                            f"Ingress CIDR opened to 0.0.0.0/0 on ports {from_port}-{to_port}."
                        ],
                        reasoning=(
                            f"Ingress rule '{rc.address}' exposes access to public internet "
                            "(0.0.0.0/0), widening the external attack surface."
                        ),
                        confidence=ConfidenceLevel.VERIFIED,
                        limitations="Evaluates CIDR patterns; does not evaluate upstream WAF.",
                        remediation=(
                            "Restrict CIDR blocks to corporate VPCs or designated bastion IPs."
                        ),
                    )
                )

        return findings


class RuleMissingDependencyEvidence(BaseRiskRule):
    """RULE-007: Missing dependency evidence for high-impact change."""

    rule_id = "RULE-007"
    name = "Missing Dependency Evidence"
    description = (
        "Warns when a destructive change involves resources with incomplete dependency data."
    )

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        for radius in impact_report.resource_blast_radii:
            if radius.is_destructive and len(radius.missing_evidence_warnings) > 0:
                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{radius.resource_address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=RiskSeverity.MEDIUM,
                        resource_address=radius.resource_address,
                        proposed_action=radius.action,
                        evidence=radius.missing_evidence_warnings,
                        reasoning=(
                            f"Destructive change on '{radius.resource_address}' has incomplete "
                            "dependency evidence. Some downstream impacts may be unverified."
                        ),
                        confidence=ConfidenceLevel.MEDIUM,
                        limitations="Dependency data is limited to the uploaded plan.",
                        remediation=(
                            "Inspect live state or upstream modules to verify all dependencies."
                        ),
                    )
                )

        return findings


class RulePlanIntegrityWarnings(BaseRiskRule):
    """RULE-008: Incomplete or unanalyzable plan structure."""

    rule_id = "RULE-008"
    name = "Plan Integrity Warnings"
    description = "Flags parsing warnings or unsupported action combinations."

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> list[RiskFinding]:
        findings: list[RiskFinding] = []

        if not plan.is_valid:
            findings.append(
                RiskFinding(
                    id=f"FINDING-{self.rule_id}-invalid-plan",
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=RiskSeverity.CRITICAL,
                    resource_address="plan",
                    proposed_action=NormalizedAction.UNSUPPORTED,
                    evidence=plan.warnings,
                    reasoning="The Terraform plan JSON is structurally invalid or malformed.",
                    confidence=ConfidenceLevel.VERIFIED,
                    limitations="Parser failed to process the plan.",
                    remediation="Generate a valid plan JSON using 'terraform show -json tfplan'.",
                )
            )
            return findings

        # Check for unsupported actions
        for rc in plan.resource_changes:
            if rc.normalized_action == NormalizedAction.UNSUPPORTED:
                findings.append(
                    RiskFinding(
                        id=f"FINDING-{self.rule_id}-{rc.address}",
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=RiskSeverity.MEDIUM,
                        resource_address=rc.address,
                        proposed_action=rc.normalized_action,
                        evidence=[f"Unrecognized actions: {rc.raw_actions}"],
                        reasoning=f"Resource '{rc.address}' has unsupported action combination.",
                        confidence=ConfidenceLevel.LOW,
                        limitations="Action behavior cannot be reliably predicted.",
                        remediation="Check Terraform CLI version compatibility.",
                    )
                )

        return findings
