"""Module F: Deterministic risk scoring and decision gating engine."""

import logging
from collections import Counter

from blast_radius.graph.builder import DependencyGraph
from blast_radius.models.graph import ConfidenceLevel
from blast_radius.models.impact import ImpactAnalysisReport
from blast_radius.models.plan import ParsedPlan
from blast_radius.models.risk import (
    DecisionStatus,
    RiskEvaluationResult,
    RiskFinding,
    RiskScoreBreakdown,
    RiskSeverity,
)
from blast_radius.rules.base import BaseRiskRule
from blast_radius.rules.catalog import (
    RuleCriticalResourceDeletion,
    RuleDestructionWithDependents,
    RuleMissingDependencyEvidence,
    RuleMultipleDestructiveActions,
    RulePlanIntegrityWarnings,
    RuleProtectionRemoval,
    RuleResourceReplacementWithDependents,
    RuleSensitiveAccessModification,
)

logger = logging.getLogger("blast_radius.scoring")

# Documented deterministic severity weights
SEVERITY_WEIGHTS: dict[RiskSeverity, float] = {
    RiskSeverity.CRITICAL: 40.0,
    RiskSeverity.HIGH: 20.0,
    RiskSeverity.MEDIUM: 10.0,
    RiskSeverity.LOW: 3.0,
    RiskSeverity.INFO: 0.0,
}

CONFIDENCE_MULTIPLIERS: dict[ConfidenceLevel, float] = {
    ConfidenceLevel.VERIFIED: 1.0,
    ConfidenceLevel.HIGH: 0.95,
    ConfidenceLevel.MEDIUM: 0.85,
    ConfidenceLevel.LOW: 0.70,
    ConfidenceLevel.UNKNOWN: 0.60,
}


class RiskScoringEngine:
    """Evaluates safety rules, computes explainable risk scores, and determines CI/CD gating."""

    DEFAULT_RULES: list[BaseRiskRule] = [
        RuleCriticalResourceDeletion(),
        RuleDestructionWithDependents(),
        RuleResourceReplacementWithDependents(),
        RuleMultipleDestructiveActions(),
        RuleProtectionRemoval(),
        RuleSensitiveAccessModification(),
        RuleMissingDependencyEvidence(),
        RulePlanIntegrityWarnings(),
    ]

    def __init__(self, rules: list[BaseRiskRule] | None = None):
        self.rules = rules or self.DEFAULT_RULES

    def evaluate(
        self,
        plan: ParsedPlan,
        graph: DependencyGraph,
        impact_report: ImpactAnalysisReport,
        critical_resources: set[str] | None = None,
    ) -> RiskEvaluationResult:
        """Run all registered safety rules, calculate score, and determine gate status."""
        all_findings: list[RiskFinding] = []

        # 1. Execute each deterministic rule
        for rule in self.rules:
            try:
                rule_findings = rule.evaluate(
                    plan=plan,
                    graph=graph,
                    impact_report=impact_report,
                    critical_resources=critical_resources,
                )
                all_findings.extend(rule_findings)
            except Exception as exc:
                logger.error(f"Rule {rule.rule_id} evaluation failed: {exc}", exc_info=True)

        # 2. Count findings by severity
        severity_counts: Counter[str] = Counter()
        for f in all_findings:
            severity_counts[f.severity.value] += 1

        # 3. Calculate deterministic risk score breakdown
        breakdown = self.calculate_score(all_findings, impact_report)

        # 4. Determine overall decision status
        decision_status, decision_reason = self.determine_decision(
            plan=plan,
            findings=all_findings,
            score=breakdown.final_score,
            has_destructive_impact=impact_report.has_destructive_impact,
        )

        return RiskEvaluationResult(
            decision_status=decision_status,
            decision_reason=decision_reason,
            risk_score=breakdown.final_score,
            score_breakdown=breakdown,
            severity_counts=dict(severity_counts),
            findings=all_findings,
            metadata={
                "total_rules_evaluated": len(self.rules),
                "total_findings": len(all_findings),
            },
        )

    def calculate_score(
        self,
        findings: list[RiskFinding],
        impact_report: ImpactAnalysisReport,
    ) -> RiskScoreBreakdown:
        """Calculate an explainable, bounded risk score on a 0.0 to 100.0 scale."""
        if not findings:
            return RiskScoreBreakdown(
                base_score=0.0,
                blast_radius_multiplier=1.0,
                confidence_factor=1.0,
                final_score=0.0,
                formula="No risk findings detected (base=0.0, blast_mult=1.0, score=0.0).",
            )

        # Raw base severity sum
        base_score = sum(SEVERITY_WEIGHTS.get(f.severity, 0.0) for f in findings)

        # Downstream blast radius multiplier (1.0 to 2.5 max)
        impacted_count = impact_report.total_impacted_resources
        blast_multiplier = min(2.5, 1.0 + (impacted_count * 0.15))

        # Evidence confidence factor
        conf_scores = [CONFIDENCE_MULTIPLIERS.get(f.confidence, 1.0) for f in findings]
        avg_confidence = sum(conf_scores) / len(conf_scores) if conf_scores else 1.0

        # Final score bounded to [0.0, 100.0]
        unbounded_score = base_score * blast_multiplier * avg_confidence
        final_score = min(100.0, max(0.0, round(unbounded_score, 1)))

        formula = (
            f"min(100, round(base({base_score}) * blast_mult({blast_multiplier:.2f}) "
            f"* conf({avg_confidence:.2f}), 1)) = {final_score}"
        )

        return RiskScoreBreakdown(
            base_score=round(base_score, 1),
            blast_radius_multiplier=round(blast_multiplier, 2),
            confidence_factor=round(avg_confidence, 2),
            final_score=final_score,
            formula=formula,
        )

    @staticmethod
    def determine_decision(
        plan: ParsedPlan,
        findings: list[RiskFinding],
        score: float,
        has_destructive_impact: bool,
    ) -> tuple[DecisionStatus, str]:
        """Determine decision status based on structural validity, findings, and score."""
        if not plan.is_valid:
            return (
                DecisionStatus.ANALYSIS_INCOMPLETE,
                "Terraform plan could not be analyzed due to structural or parsing errors.",
            )

        has_critical = any(f.severity == RiskSeverity.CRITICAL for f in findings)
        if has_critical:
            crit_count = sum(1 for f in findings if f.severity == RiskSeverity.CRITICAL)
            return (
                DecisionStatus.BLOCKED,
                f"Deployment blocked: {crit_count} CRITICAL safety rule violation(s) detected.",
            )

        if score >= 80.0:
            return (
                DecisionStatus.BLOCKED,
                f"Deployment blocked: Overall risk score ({score}) exceeds threshold (80.0).",
            )

        has_high = any(f.severity == RiskSeverity.HIGH for f in findings)
        if has_high or has_destructive_impact or score >= 30.0:
            reasons = []
            if has_high:
                reasons.append("HIGH severity findings")
            if has_destructive_impact:
                reasons.append("destructive downstream impacts")
            if score >= 30.0:
                reasons.append(f"risk score ({score}) >= review threshold (30.0)")
            return (
                DecisionStatus.REVIEW_REQUIRED,
                f"Manual review required due to: {', '.join(reasons)}.",
            )

        return (
            DecisionStatus.PASS,
            "Plan passed all deterministic safety checks. No high or critical risks identified.",
        )
