"""Unit tests for the CLI entrypoint (blast-radius / blast_radius.cli)."""

import json
from pathlib import Path

from blast_radius import __version__
from blast_radius.cli import (
    EXIT_GATE_FAILED,
    EXIT_INPUT_ERROR,
    EXIT_SUCCESS,
    run_cli,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_cli_version(capsys):
    """Verify 'version' subcommand outputs current version and exits 0."""
    code = run_cli(["version"])
    assert code == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert f"blast-radius v{__version__}" in captured.out


def test_cli_no_args(capsys):
    """Verify running CLI without arguments prints help and returns exit code 2."""
    code = run_cli([])
    assert code == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert "usage:" in captured.out or "usage:" in captured.err or "Predictive" in captured.out


def test_cli_clean_plan_passes(capsys):
    """Verify clean resource addition passes CI gate with exit code 0."""
    plan_file = str(FIXTURES_DIR / "add_resource.json")
    code = run_cli(["analyze", plan_file, "--fail-on=blocked"])
    assert code == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "[ PASS ]" in captured.out
    assert "Risk Score        : 0.0/100.0" in captured.out


def test_cli_fail_on_review_required(capsys):
    """Verify dangerous plan triggers exit code 1 with --fail-on=review_required."""
    plan_file = str(FIXTURES_DIR / "delete_with_dependents.json")
    code = run_cli(["analyze", plan_file, "--fail-on=review_required"])
    assert code == EXIT_GATE_FAILED
    captured = capsys.readouterr()
    assert "[ REVIEW_REQUIRED ]" in captured.out
    assert "CI GATE FAILED" in captured.err


def test_cli_fail_on_blocked_passes_on_review_required(capsys):
    """Verify review_required plan passes when gating threshold is strictly --fail-on=blocked."""
    plan_file = str(FIXTURES_DIR / "delete_with_dependents.json")
    code = run_cli(["analyze", plan_file, "--fail-on=blocked"])
    assert code == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "[ REVIEW_REQUIRED ]" in captured.out


def test_cli_fail_on_blocked_fails_when_critical_violated(capsys):
    """Verify critical resource deletion breaches --fail-on=blocked gate with exit 1."""
    plan_file = str(FIXTURES_DIR / "delete_with_dependents.json")
    code = run_cli(
        [
            "analyze",
            plan_file,
            "--critical",
            "aws_db_instance.primary",
            "--fail-on=blocked",
        ]
    )
    assert code == EXIT_GATE_FAILED
    captured = capsys.readouterr()
    assert "[ BLOCKED ]" in captured.out
    assert "RULE-001" in captured.out
    assert "CI GATE FAILED" in captured.err


def test_cli_max_score_gate_exceeded(capsys):
    """Verify plan exceeding --max-score threshold exits with code 1."""
    plan_file = str(FIXTURES_DIR / "delete_with_dependents.json")
    # Plan has risk score 26.0, threshold is 15.0
    code = run_cli(["analyze", plan_file, "--max-score", "15.0"])
    assert code == EXIT_GATE_FAILED
    captured = capsys.readouterr()
    assert "exceeds maximum threshold 15.0" in captured.err


def test_cli_missing_file_error(capsys):
    """Verify non-existent plan file returns exit code 2."""
    code = run_cli(["analyze", "/tmp/does_not_exist_tfplan.json"])
    assert code == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert "Plan file not found" in captured.err


def test_cli_malformed_plan_error(capsys):
    """Verify malformed JSON input returns exit code 2 (incomplete)."""
    plan_file = str(FIXTURES_DIR / "malformed.json")
    code = run_cli(["analyze", plan_file])
    assert code == EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    assert "[ ANALYSIS_INCOMPLETE ]" in captured.out


def test_cli_markdown_file_export(tmp_path):
    """Verify --format=markdown -o <path> writes valid markdown report."""
    plan_file = str(FIXTURES_DIR / "replace_with_dependents.json")
    out_file = tmp_path / "pr_comment.md"
    code = run_cli(
        [
            "analyze",
            plan_file,
            "--format=markdown",
            "--output",
            str(out_file),
            "--quiet",
        ]
    )
    assert code == EXIT_SUCCESS
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "# Cloud Blast-Radius Simulation Report" in content
    assert "aws_subnet.private_app" in content


def test_cli_json_export(capsys):
    """Verify --format=json outputs valid sanitized JSON."""
    plan_file = str(FIXTURES_DIR / "replace_with_dependents.json")
    code = run_cli(["analyze", plan_file, "--format=json"])
    assert code == EXIT_SUCCESS
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["decision_status"] == "review_required"
    assert "aws_subnet.private_app" in [
        r["resource_address"] for r in data["impact_summary"]["resource_blast_radii"]
    ]


def test_cli_stdin_input(monkeypatch, capsys):
    """Verify reading plan from standard input ('-')."""
    plan_bytes = (FIXTURES_DIR / "add_resource.json").read_bytes()
    monkeypatch.setattr("sys.stdin.buffer.read", lambda: plan_bytes)
    code = run_cli(["analyze", "-"])
    assert code == EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "[ PASS ]" in captured.out
