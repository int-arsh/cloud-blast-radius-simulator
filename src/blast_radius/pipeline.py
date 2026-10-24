"""End-to-end analysis pipeline orchestrator."""

import logging
import uuid
from datetime import UTC, datetime

from blast_radius import __version__
from blast_radius.cloud.client import CloudEnricher
from blast_radius.config import get_settings
from blast_radius.graph.builder import DependencyGraph
from blast_radius.impact.analyzer import ImpactAnalyzer
from blast_radius.models.cloud import CloudEnrichmentReport
from blast_radius.models.impact import ImpactAnalysisReport
from blast_radius.models.report import FullAnalysisReport
from blast_radius.models.risk import (
    DecisionStatus,
    RiskScoreBreakdown,
)
from blast_radius.parser.terraform import TerraformPlanParser
from blast_radius.scoring.engine import RiskScoringEngine
from blast_radius.validation.validator import PlanValidator

logger = logging.getLogger("blast_radius.pipeline")


class BlastRadiusPipeline:
    """Orchestrates input validation, plan parsing, graph modeling, impact analysis, and scoring."""

    def __init__(
        self,
        validator: PlanValidator | None = None,
        parser: TerraformPlanParser | None = None,
        scoring_engine: RiskScoringEngine | None = None,
    ):
        self.validator = validator or PlanValidator()
        self.parser = parser or TerraformPlanParser(validator=self.validator)
        self.scoring_engine = scoring_engine or RiskScoringEngine()

    def run_analysis(
        self,
        content: bytes | str,
        critical_resources: set[str] | None = None,
        cloud_enricher: CloudEnricher | None = None,
    ) -> FullAnalysisReport:
        """Execute complete analysis pipeline from raw plan payload."""
        run_id = f"sim-{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(UTC).isoformat()
        settings = get_settings()

        # Step 1: Input Validation
        validation = self.validator.validate_raw(content)
        if not validation.is_valid or validation.data is None:
            return self._build_incomplete_report(
                run_id=run_id,
                timestamp=timestamp,
                validation_errors=validation.errors,
                validation_warnings=validation.warnings,
            )

        # Step 2: Plan Parsing & Change Normalization
        parsed_plan = self.parser.parse_dict(validation.data, initial_warnings=validation.warnings)
        if not parsed_plan.is_valid:
            return self._build_incomplete_report(
                run_id=run_id,
                timestamp=timestamp,
                validation_errors=parsed_plan.warnings,
                validation_warnings=[],
            )

        # Step 3: Dependency Graph Construction
        graph = DependencyGraph.from_parsed_plan(parsed_plan)
        graph_stats = graph.analyze()

        # Step 4: Downstream Blast Radius & Impact Analysis
        impact_analyzer = ImpactAnalyzer(graph)
        impact_report = impact_analyzer.analyze_plan(parsed_plan)

        # Step 5: Deterministic Safety Rules & Scoring Evaluation
        evaluation = self.scoring_engine.evaluate(
            plan=parsed_plan,
            graph=graph,
            impact_report=impact_report,
            critical_resources=critical_resources,
        )

        # Step 6: Live Cloud State Enrichment (Optional, Safe Read-Only)
        enrichment_report: CloudEnrichmentReport | None = None
        decision_status = evaluation.decision_status
        decision_reason = evaluation.decision_reason

        if cloud_enricher is not None:
            enrichment_report = cloud_enricher.enrich_plan(parsed_plan)
            # Elevate PASS to REVIEW_REQUIRED if live safeguards or production violations detected
            if enrichment_report.production_violations:
                if decision_status == DecisionStatus.PASS:
                    decision_status = DecisionStatus.REVIEW_REQUIRED
                    decision_reason = (
                        "Live cloud safeguard violation: planned destructive change targeting "
                        "live production-tagged resource."
                    )
            elif enrichment_report.protection_warnings and decision_status == DecisionStatus.PASS:
                decision_status = DecisionStatus.REVIEW_REQUIRED
                decision_reason = (
                    "Live cloud safeguards active: deletion/termination protection enabled on "
                    "resources slated for destroy/replacement."
                )

        # Step 7: Compile Full Report
        unique_remediations = sorted({f.remediation for f in evaluation.findings})
        all_warnings_list = list(parsed_plan.warnings + impact_report.missing_information_warnings)
        if enrichment_report:
            all_warnings_list.extend(enrichment_report.protection_warnings)
            all_warnings_list.extend(enrichment_report.production_violations)
            for state in enrichment_report.resource_states.values():
                all_warnings_list.extend(state.drift_messages)

        all_warnings = sorted(set(all_warnings_list))

        resource_counts = {
            "total": graph_stats.total_nodes,
            "changed": impact_report.total_changed_resources,
            "impacted": impact_report.total_impacted_resources,
            "unaffected": impact_report.unaffected_resource_count,
        }

        dependency_counts = {
            "nodes": graph_stats.total_nodes,
            "edges": graph_stats.total_edges,
            "cycles": len(graph_stats.cycles),
            "isolated": len(graph_stats.isolated_nodes),
            "missing": len(graph_stats.missing_dependencies),
        }

        return FullAnalysisReport(
            analysis_id=run_id,
            timestamp=timestamp,
            engine_version=__version__,
            format_version=parsed_plan.format_version,
            terraform_version=parsed_plan.terraform_version,
            decision_status=decision_status,
            decision_reason=decision_reason,
            risk_score=evaluation.risk_score,
            score_breakdown=evaluation.score_breakdown,
            resource_counts=resource_counts,
            action_counts=parsed_plan.action_counts,
            dependency_counts=dependency_counts,
            severity_counts=evaluation.severity_counts,
            impact_summary=impact_report,
            nodes=graph.get_all_nodes(),
            edges=graph.get_all_edges(),
            findings=evaluation.findings,
            warnings=all_warnings,
            remediations=unique_remediations,
            cloud_enrichment=enrichment_report,
            metadata={
                "environment": settings.environment,
                "cycles_detected": len(graph_stats.cycles) > 0,
            },
        )

    @staticmethod
    def _build_incomplete_report(
        run_id: str,
        timestamp: str,
        validation_errors: list[str],
        validation_warnings: list[str],
    ) -> FullAnalysisReport:
        """Create structured report for unanalyzable or malformed inputs."""
        all_warnings = validation_errors + validation_warnings
        empty_impact = ImpactAnalysisReport(
            total_changed_resources=0,
            total_impacted_resources=0,
            direct_impact_count=0,
            transitive_impact_count=0,
            unaffected_resource_count=0,
            resource_blast_radii=[],
            unique_impacted_addresses=[],
            missing_information_warnings=all_warnings,
            has_destructive_impact=False,
        )

        breakdown = RiskScoreBreakdown(
            base_score=0.0,
            blast_radius_multiplier=1.0,
            confidence_factor=0.0,
            final_score=0.0,
            formula="Analysis incomplete due to validation/parsing failure.",
        )

        return FullAnalysisReport(
            analysis_id=run_id,
            timestamp=timestamp,
            engine_version=__version__,
            format_version="unknown",
            terraform_version=None,
            decision_status=DecisionStatus.ANALYSIS_INCOMPLETE,
            decision_reason=(
                "Analysis could not be completed: input payload is malformed or invalid."
            ),
            risk_score=0.0,
            score_breakdown=breakdown,
            resource_counts={"total": 0, "changed": 0, "unaffected": 0},
            action_counts={},
            dependency_counts={"nodes": 0, "edges": 0, "cycles": 0},
            severity_counts={},
            impact_summary=empty_impact,
            findings=[],
            warnings=all_warnings,
            remediations=["Provide a structurally valid Terraform plan JSON."],
            metadata={"status": "analysis_incomplete"},
        )
