"""Module G: Human-readable Markdown and text report generator."""

from blast_radius.models.report import FullAnalysisReport


class MarkdownReporter:
    """Generates human-readable Markdown reports suitable for PR comments and terminal display."""

    @staticmethod
    def generate_markdown(report: FullAnalysisReport) -> str:
        """Render a FullAnalysisReport into formatted Markdown."""
        lines: list[str] = []

        # 1. Header & Status
        status_icons = {
            "pass": "PASSED",
            "review_required": "REVIEW REQUIRED",
            "blocked": "BLOCKED",
            "analysis_incomplete": "ANALYSIS INCOMPLETE",
        }
        status_label = status_icons.get(
            report.decision_status.value, report.decision_status.value.upper()
        )

        lines.append(f"# Cloud Blast-Radius Simulation Report: [{status_label}]")
        lines.append("")
        lines.append(
            f"**Decision Status:** `{report.decision_status.value}` — {report.decision_reason}"
        )
        lines.append(f"**Overall Risk Score:** `{report.risk_score} / 100.0`")
        lines.append(
            f"**Analysis ID:** `{report.analysis_id}` | **Executed:** `{report.timestamp}`"
        )
        tf_ver = report.terraform_version or "N/A"
        lines.append(f"**Terraform Version:** `{tf_ver}` (Format: `{report.format_version}`)")
        lines.append("")

        # 2. Score Breakdown
        lines.append("## 1. Risk Score Breakdown")
        lines.append(f"- **Severity Base Score:** `{report.score_breakdown.base_score}`")
        lines.append(
            f"- **Blast Radius Multiplier:** `{report.score_breakdown.blast_radius_multiplier}x`"
        )
        lines.append(f"- **Confidence Factor:** `{report.score_breakdown.confidence_factor}x`")
        lines.append(f"- **Formula:** `{report.score_breakdown.formula}`")
        lines.append("")

        # 3. Resource & Action Summary Table
        lines.append("## 2. Infrastructure Changes & Blast Scope")
        lines.append("| Metric | Count |")
        lines.append("| :--- | :--- |")
        lines.append(f"| Total Resources in Plan | {report.resource_counts.get('total', 0)} |")
        lines.append(
            f"| Resources Slated for Change | {report.resource_counts.get('changed', 0)} |"
        )
        lines.append(
            f"| Downstream Impacted Resources | {report.impact_summary.total_impacted_resources} |"
        )
        lines.append(f"| Direct Dependent Links | {report.impact_summary.direct_impact_count} |")
        lines.append(
            f"| Transitive Cascade Links | {report.impact_summary.transitive_impact_count} |"
        )
        lines.append(f"| Unaffected Resources | {report.resource_counts.get('unaffected', 0)} |")
        lines.append("")

        # Action breakdown
        lines.append(
            "**Actions Breakdown:** "
            + ", ".join(f"`{act}`: {cnt}" for act, cnt in report.action_counts.items())
        )
        lines.append("")

        # 4. Downstream Impacted Resources
        lines.append("## 3. Downstream Impact Detail")
        if report.impact_summary.total_impacted_resources == 0:
            lines.append(
                "No downstream infrastructure dependencies are impacted by the proposed changes."
            )
        else:
            lines.append(
                "| Impacted Resource | Type | Triggering Change | Path Hops | Failure Scenario |"
            )
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for radius in report.impact_summary.resource_blast_radii:
                for imp in radius.impacted_resources:
                    lines.append(
                        f"| `{imp.address}` | `{imp.impact_type.value}` | "
                        f"`{imp.triggering_resource}` ({imp.triggering_action.value}) | "
                        f"{imp.path_length} | {imp.potential_failure_scenario} |"
                    )
        lines.append("")

        # 5. Risk Findings
        lines.append("## 4. Evidence-Backed Risk Findings")
        if not report.findings:
            lines.append("No risk findings detected. All deterministic safety policies passed.")
        else:
            for idx, finding in enumerate(report.findings, 1):
                sev = finding.severity.value.upper()
                lines.append(
                    f"### Finding {idx}: [{sev}] {finding.rule_name} (`{finding.rule_id}`)"
                )
                lines.append(
                    f"- **Resource:** `{finding.resource_address}` ({finding.proposed_action})"
                )
                lines.append(f"- **Reasoning:** {finding.reasoning}")
                lines.append(f"- **Evidence:** {'; '.join(finding.evidence)}")
                lines.append(f"- **Remediation:** {finding.remediation}")
                lines.append(
                    f"- **Confidence:** `{finding.confidence.value}` | "
                    f"**Limitations:** {finding.limitations}"
                )
                lines.append("")

        # 6. Warnings & Limitations
        if report.warnings or report.impact_summary.missing_information_warnings:
            lines.append("## 5. Warnings & Missing Evidence")
            all_warnings = report.warnings + report.impact_summary.missing_information_warnings
            for warn in all_warnings:
                lines.append(f"- {warn}")
            lines.append("")

        # 7. Actionable Next Steps
        lines.append("## 6. Recommended Next Steps")
        if report.decision_status.value == "blocked":
            lines.append(
                "- **DO NOT APPLY:** Resolve all CRITICAL findings and obtain security approval."
            )
        elif report.decision_status.value == "review_required":
            lines.append(
                "- **MANUAL REVIEW:** Inspect blast radius and confirm maintenance window."
            )
        elif report.decision_status.value == "analysis_incomplete":
            lines.append("- **RE-RUN ANALYSIS:** Re-export plan using `terraform show -json`.")
        else:
            lines.append(
                "- **SAFE TO PROCEED:** Plan passes automated deterministic safety baseline."
            )

        return "\n".join(lines)
