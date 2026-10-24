"""Command-line interface (CLI) for Cloud Blast-Radius Simulator.

Enables automated CI/CD pipeline gating, pull request reporting,
and deterministic cloud infrastructure change simulation.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from blast_radius import __version__
from blast_radius.models.risk import DecisionStatus
from blast_radius.pipeline import BlastRadiusPipeline
from blast_radius.reporting.json_reporter import JsonReporter
from blast_radius.reporting.markdown_reporter import MarkdownReporter

# Exit code conventions for CI/CD pipelines
EXIT_SUCCESS = 0
EXIT_GATE_FAILED = 1
EXIT_INPUT_ERROR = 2


def _supports_color() -> bool:
    """Determine whether terminal supports ANSI color output."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _color(text: str, code: str) -> str:
    """Format string with ANSI escape code if color is supported."""
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for the blast-radius CLI."""
    parser = argparse.ArgumentParser(
        prog="blast-radius",
        description="Predictive Cloud Infrastructure Blast-Radius Simulator & CI Gate",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Command: version
    subparsers.add_parser("version", help="Print simulator version and exit")

    # Command: analyze
    analyze_parser = subparsers.add_parser(
        "analyze", help="Simulate blast radius and evaluate risk gates for a plan"
    )
    analyze_parser.add_argument(
        "plan_file",
        help="Path to Terraform plan JSON file (or '-' to read from standard input)",
    )
    analyze_parser.add_argument(
        "--fail-on",
        choices=["blocked", "review_required", "never"],
        default="blocked",
        help=(
            "Gating threshold that triggers a non-zero exit code (default: 'blocked'). "
            "'review_required' fails on both REVIEW_REQUIRED and BLOCKED."
        ),
    )
    analyze_parser.add_argument(
        "--max-score",
        type=float,
        default=None,
        help="Maximum permissible risk score (0.0 to 100.0). Breaching triggers exit 1.",
    )
    analyze_parser.add_argument(
        "--critical",
        action="append",
        dest="critical_resources",
        default=[],
        help="Resource addresses designated as mission-critical (repeatable or comma-separated).",
    )
    analyze_parser.add_argument(
        "--format",
        choices=["summary", "markdown", "json"],
        default="summary",
        help="Report format to emit (default: summary).",
    )
    analyze_parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Path to file where report should be written (e.g. pr-comment.md).",
    )
    analyze_parser.add_argument(
        "--enrich-aws",
        action="store_true",
        help="Enrich plan analysis with live AWS cloud state (strictly read-only).",
    )
    analyze_parser.add_argument(
        "--aws-profile",
        type=str,
        default=None,
        help="AWS profile name for live cloud authentication.",
    )
    analyze_parser.add_argument(
        "--aws-region",
        type=str,
        default=None,
        help="AWS region for live cloud inspection (e.g. us-east-1).",
    )
    analyze_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress terminal output (useful when output is directed to a file).",
    )

    return parser


def format_summary(report) -> str:
    """Format a clean, concise, colored terminal summary for human inspection."""
    status_str = report.decision_status.value.upper()
    if report.decision_status == DecisionStatus.PASS:
        badge = _color(f"[ {status_str} ]", "1;32")
    elif report.decision_status == DecisionStatus.REVIEW_REQUIRED:
        badge = _color(f"[ {status_str} ]", "1;33")
    elif report.decision_status == DecisionStatus.BLOCKED:
        badge = _color(f"[ {status_str} ]", "1;31")
    else:
        badge = _color(f"[ {status_str} ]", "1;37")

    score_str = f"{report.risk_score:.1f}/100.0"
    if report.risk_score >= 80.0:
        colored_score = _color(score_str, "1;31")
    elif report.risk_score >= 30.0:
        colored_score = _color(score_str, "1;33")
    else:
        colored_score = _color(score_str, "1;32")

    lines = [
        "=" * 72,
        f"  CLOUD BLAST-RADIUS SIMULATION  |  Engine v{report.engine_version}",
        "=" * 72,
        f" Gate Status       : {badge}",
        f" Risk Score        : {colored_score}",
        f" Decision Reason   : {report.decision_reason}",
        "-" * 72,
        f" Total Resources   : {report.resource_counts.get('total', 0)}",
        f" Planned Changes   : {report.resource_counts.get('changed', 0)} ({report.action_counts})",
        f" Impacted Nodes    : {report.impact_summary.total_impacted_resources} "
        f"(Direct: {report.impact_summary.direct_impact_count}, "
        f"Transitive: {report.impact_summary.transitive_impact_count})",
        f" Graph Cycles      : {report.dependency_counts.get('cycles', 0)}",
        "-" * 72,
    ]

    if report.findings:
        lines.append(f" Findings ({len(report.findings)} safety rule violations):")
        for finding in report.findings:
            sev = finding.severity.upper()
            if sev == "CRITICAL":
                sev_label = _color(sev, "1;31")
            elif sev == "HIGH":
                sev_label = _color(sev, "1;33")
            else:
                sev_label = _color(sev, "1;34")
            lines.append(f"   [{sev_label}] {finding.rule_id}: {finding.rule_name}")
            lines.append(f"          Target  : {finding.resource_address}")
            lines.append(f"          Remedy  : {finding.remediation}")
        lines.append("-" * 72)
    else:
        lines.append(_color(" Clean Plan: Zero safety rule violations detected.", "1;32"))
        lines.append("-" * 72)

    if report.cloud_enrichment:
        ce = report.cloud_enrichment
        auth_status = "Authenticated" if ce.authenticated else "Offline / Simulation"
        lines.append(f" Live AWS Cloud    : {auth_status} (Region: {ce.region or 'us-east-1'})")
        lines.append(
            f" Resources Checked : {ce.resources_checked} "
            f"(Exist: {ce.resources_existing}, Missing: {ce.resources_missing}, "
            f"Drift: {ce.drift_count})"
        )
        if ce.protection_warnings:
            lines.append(" Active Safeguards :")
            for pw in ce.protection_warnings:
                lines.append(f"   {_color('[SAFEGUARD]', '1;33')} {pw}")
        if ce.production_violations:
            lines.append(" Production Violations:")
            for pv in ce.production_violations:
                lines.append(f"   {_color('[PROD-VIOLATION]', '1;31')} {pv}")
        lines.append("-" * 72)

    return "\n".join(lines)


def run_cli(args: Sequence[str] | None = None) -> int:
    """Execute the CLI logic and return appropriate exit code."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.subcommand:
        parser.print_help()
        return EXIT_INPUT_ERROR

    if parsed.subcommand == "version":
        print(f"blast-radius v{__version__}")
        return EXIT_SUCCESS

    if parsed.subcommand == "analyze":
        # 1. Read input plan bytes
        plan_path = parsed.plan_file
        if plan_path == "-":
            raw_bytes = sys.stdin.buffer.read()
        else:
            path = Path(plan_path)
            if not path.is_file():
                sys.stderr.write(f"Error: Plan file not found: {plan_path}\n")
                return EXIT_INPUT_ERROR
            try:
                raw_bytes = path.read_bytes()
            except OSError as err:
                sys.stderr.write(f"Error reading {plan_path}: {err}\n")
                return EXIT_INPUT_ERROR

        if not raw_bytes:
            sys.stderr.write("Error: Empty plan input received.\n")
            return EXIT_INPUT_ERROR

        # 2. Parse critical resources list
        critical_set: set[str] = set()
        for item in parsed.critical_resources:
            for part in item.split(","):
                part_clean = part.strip()
                if part_clean:
                    critical_set.add(part_clean)

        # 3. Initialize Cloud Enricher if requested
        cloud_enricher = None
        if parsed.enrich_aws:
            from blast_radius.cloud.client import CloudEnricher

            cloud_enricher = CloudEnricher(
                profile=parsed.aws_profile,
                region=parsed.aws_region,
            )

        # 4. Execute Analysis Pipeline
        pipeline = BlastRadiusPipeline()
        report = pipeline.run_analysis(
            raw_bytes,
            critical_resources=critical_set if critical_set else None,
            cloud_enricher=cloud_enricher,
        )

        # 4. Format Output
        if parsed.format == "json":
            output_content = JsonReporter.generate_json(report)
        elif parsed.format == "markdown":
            output_content = MarkdownReporter.generate_markdown(report)
        else:
            output_content = format_summary(report)

        # Write to file if requested
        if parsed.output:
            try:
                out_path = Path(parsed.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(output_content, encoding="utf-8")
            except OSError as err:
                sys.stderr.write(f"Error writing output file {parsed.output}: {err}\n")
                return EXIT_INPUT_ERROR

        # Print to stdout unless quieted
        if not parsed.quiet:
            print(output_content)

        # 5. Evaluate Gating Decisions
        # If input was malformed or incomplete, return EXIT_INPUT_ERROR
        if report.decision_status == DecisionStatus.ANALYSIS_INCOMPLETE:
            return EXIT_INPUT_ERROR

        # Check maximum score threshold
        if parsed.max_score is not None and report.risk_score > parsed.max_score:
            if not parsed.quiet:
                sys.stderr.write(
                    f"\n[CI GATE FAILED] Risk score {report.risk_score:.1f} "
                    f"exceeds maximum threshold {parsed.max_score:.1f}.\n"
                )
            return EXIT_GATE_FAILED

        # Check fail-on status threshold
        if parsed.fail_on == "review_required":
            if report.decision_status in (
                DecisionStatus.REVIEW_REQUIRED,
                DecisionStatus.BLOCKED,
            ):
                if not parsed.quiet:
                    sys.stderr.write(
                        f"\n[CI GATE FAILED] Decision status is '{report.decision_status.value}' "
                        f"(fail-on threshold: '{parsed.fail_on}').\n"
                    )
                return EXIT_GATE_FAILED
        elif parsed.fail_on == "blocked":
            if report.decision_status == DecisionStatus.BLOCKED:
                if not parsed.quiet:
                    sys.stderr.write(
                        "\n[CI GATE FAILED] Decision status is 'BLOCKED' "
                        "(fail-on threshold: 'blocked').\n"
                    )
                return EXIT_GATE_FAILED

        return EXIT_SUCCESS

    return EXIT_INPUT_ERROR


def main() -> None:
    """Main CLI entrypoint invoked by python scripts or shell."""
    exit_code = run_cli()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
