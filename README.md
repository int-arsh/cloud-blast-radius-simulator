# Cloud Blast-Radius Simulator

<p align="center">
  <strong>Predictive Cloud Infrastructure Blast-Radius Simulator & Automated CI/CD Policy Gate</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-blue.svg" alt="Python 3.13" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB.svg?logo=react" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-5.7-3178C6.svg?logo=typescript" alt="TypeScript" />
  <img src="https://img.shields.io/badge/NetworkX-3.4-orange.svg" alt="NetworkX" />
  <img src="https://img.shields.io/badge/tests-94%20passed-success.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/coverage-92%25-brightgreen.svg" alt="Coverage" />
  <img src="https://img.shields.io/badge/cloud-AWS%20Safe%20Read--Only-232F3E.svg?logo=amazon-aws" alt="AWS Read-Only" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License" />
</p>

---

## Overview

**Cloud Blast-Radius Simulator** is an automated reliability and security engine for cloud infrastructure changes. By analyzing proposed Terraform plan files (`terraform show -json tfplan.binary`) prior to deployment, it maps dependency topologies, identifies direct and transitive blast radii, detects destructive changes, computes deterministic risk scores, and gates CI/CD pipelines before `terraform apply` can cause outages.

### The Problem It Solves
1. **Unseen Cascading Outages:** Modifying a core subnet or security group in Terraform often forces an in-place resource replacement that quietly breaks dozens of decoupled upstream containers, load balancers, or DNS records.
2. **Opaque Textual Plans:** Standard `terraform plan` output can span thousands of lines of raw JSON/diffs, making manual human peer-review error-prone and slow.
3. **Absence of Pre-Apply Gating:** Native CI/CD pipelines lack automated, deterministic policy gates that block pull requests before applying high-risk or unreviewed changes.

---

## Key Capabilities

- **Deterministic Safety Engine:** Evaluates infrastructure changes against 8 deterministic reliability rules (`RULE-001` through `RULE-008`). Identical plans yield identical results—no flaky heuristics or black-box LLM decisions overriding safety policies.
- **Dependency Topology Modeling:** Constructs a directed acyclic graph (DAG) where edges strictly represent `App → DB` dependencies. Traverses downstream reachability via direct (`predecessors`) and transitive (`ancestors`) graph algorithms with cycle protection.
- **Explainable Multi-Factor Scoring:** Calculates risk scores on a 0.0 to 100.0 scale using a transparent formula combining Base Severity, Blast Radius Multiplier, and Evidence Confidence.
- **Strict Read-Only Live AWS Enrichment:** Optionally verifies live cloud state via boto3. Audits active RDS `DeletionProtection`, EC2 `DisableApiTermination`, and detects out-of-band configuration drift using strictly read-only primitives (`describe_*`, `get_*`).
- **CI/CD Pipeline Gating:** The `blast-radius` CLI provides automated evaluation with predictable exit codes (`0` for PASS, `1` for GATE_FAILED, `2` for INPUT_ERROR) and generates sticky GitHub Actions PR comment reports.
- **Interactive Web Interface:** Modern React 19 + TypeScript single-page application featuring an interactive SVG DAG visualizer, node inspector, scenario presets, and drag-and-drop plan uploads.
- **Built-in Security Invariants:** Pre-ingestion redaction filters automatically strip AWS access keys, private keys, and bearer tokens from logs and reports.

---

## Architectural Pipeline

```text
[ Terraform Plan JSON ]
           │
           ▼
[ 1. Input Validation & Secret Redaction ]
           │ (Valid plan payload, <10 MB, credentials redacted)
           ▼
[ 2. Plan Parsing & Action Normalization ]
           │ (Maps actions to CREATE, UPDATE, DELETE, REPLACE, NO_OP)
           ▼
[ 3. Dependency Graph Construction ]
           │ (Builds directed DAG: App -> Database; provenance tagged)
           ▼
[ 4. Downstream Impact Analysis ]
           │ (Direct & transitive traversal, shortest paths, failure modes)
           ▼
[ 5. Deterministic Safety Rules Evaluation ]
           │ (Executes RULE-001 through RULE-008; evidence-backed findings)
           ▼
[ 6. Explainable Risk Scoring Engine ]
           │ (Risk Score = Base Severity * Blast Multiplier * Confidence)
           ▼
[ 7. Live Cloud State Enrichment (Optional, Safe Read-Only) ]
           │ (RDS deletion protection, EC2 termination flags, drift inspection)
           ▼
[ 8. Multi-Channel Report Generation & Gating ]
   ├── Terminal CLI (ANSI colored summary cards & gate exit code 0/1/2)
   ├── Markdown Reporter (Sticky GitHub PR review comment)
   └── REST API / Frontend (JSON payload & interactive React SVG visualizer)
```

---

## Quickstart

### Option 1: Docker Compose (Zero Setup)
Launch the complete stack (FastAPI backend on port `8000` + React frontend on port `5173`):
```bash
docker compose up --build
```
Open your browser to: **`http://localhost:5173`**

---

### Option 2: Local Python & Node Setup

#### 1. Prerequisites
- Python >= 3.12 (CPython 3.13 tested)
- [uv](https://docs.astral.sh/uv/) (recommended) or standard `pip`
- Node.js >= 20

#### 2. Backend Installation & Startup
```bash
# Clone the repository
git clone https://github.com/your-org/cloud-blast-radius-simulator.git
cd cloud-blast-radius-simulator

# Create virtual environment and install package in editable mode
uv venv --python 3.13 .venv
source .venv/bin/activate
uv sync

# Run the test suite (94 tests, 92% coverage)
uv run pytest

# Start the FastAPI server
uv run uvicorn blast_radius.api.app:app --reload --port 8000
```
- API Health Check: `http://localhost:8000/health`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

#### 3. Frontend Startup
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** to access the interactive web interface.

---

## CLI Usage & CI/CD Pipeline Gating

The `blast-radius` CLI is designed for terminal inspection and automated CI/CD gating:

```bash
# Basic simulation with human-readable colored summary
blast-radius analyze tfplan.json

# Enforce CI Gate: Fail if decision status is REVIEW_REQUIRED or BLOCKED
blast-radius analyze tfplan.json --fail-on=review_required

# Enforce Maximum Permissible Risk Score
blast-radius analyze tfplan.json --max-score=50.0

# Designate mission-critical resources (triggers RULE-001 / BLOCKED on delete)
blast-radius analyze tfplan.json --critical=aws_db_instance.primary

# Export Markdown PR comment to file for GitHub Actions
blast-radius analyze tfplan.json --format=markdown -o pr_comment.md --quiet

# Optional Live AWS Cloud State Enrichment (Safe Read-Only)
blast-radius analyze tfplan.json --enrich-aws --aws-region=us-east-1
```

### CLI Terminal Output Sample
```text
========================================================================
  CLOUD BLAST-RADIUS SIMULATION  |  Engine v0.1.0
========================================================================
 Gate Status       : [ REVIEW_REQUIRED ]
 Risk Score        : 26.0/100.0
 Decision Reason   : Manual review required due to: HIGH severity findings, destructive downstream impacts.
------------------------------------------------------------------------
 Total Resources   : 3
 Planned Changes   : 1 ({'delete': 1, 'no-op': 2})
 Impacted Nodes    : 2 (Direct: 2, Transitive: 0)
 Graph Cycles      : 0
------------------------------------------------------------------------
 Findings (1 safety rule violations):
   [HIGH] RULE-002: Destruction of Resource with Known Dependents
          Target  : aws_db_instance.primary
          Remedy  : Decouple or migrate downstream dependent services prior to destroying 'aws_db_instance.primary'.
------------------------------------------------------------------------
 Live AWS Cloud    : Authenticated (Region: us-east-1)
 Resources Checked : 3 (Exist: 1, Missing: 0, Drift: 0)
 Active Safeguards :
   [SAFEGUARD] Active Safeguard: 'aws_db_instance.primary' has DeletionProtection=True in live cloud; terraform destroy/replace will be rejected by AWS.
------------------------------------------------------------------------
```

---

## Deterministic Safety Rule Catalog

| Rule ID | Rule Name | Severity | Gating Impact | Description & Trigger |
| :--- | :--- | :---: | :---: | :--- |
| **`RULE-001`** | **Critical Resource Deletion** | `CRITICAL` | `BLOCKED` | Slated deletion or replacement of a resource designated as mission-critical. |
| **`RULE-002`** | **Destruction with Dependents** | `HIGH` | `REVIEW_REQUIRED` | Slated deletion of a resource that has active downstream dependents relying on it. |
| **`RULE-003`** | **Replacement of Foundational Tier** | `HIGH` | `REVIEW_REQUIRED` | In-place replacement of foundational networking or storage tiers with active dependents. |
| **`RULE-004`** | **Multiple Destructive Actions** | `MEDIUM` | `REVIEW_REQUIRED` | Simultaneous destruction of 2+ decoupled infrastructure services in a single plan. |
| **`RULE-005`** | **Protection Removal** | `CRITICAL` | `BLOCKED` | Explicit removal of safeguards (`deletion_protection = false`, dropping termination protection). |
| **`RULE-006`** | **Sensitive Access Exposure** | `HIGH` | `REVIEW_REQUIRED` | Security group rule changes opening SSH (22), RDP (3389), or database ports to `0.0.0.0/0`. |
| **`RULE-007`** | **Uncontained Blast Radius** | `MEDIUM` | `REVIEW_REQUIRED` | A single change impacts > 50% of the entire infrastructure topology. |
| **`RULE-008`** | **Plan Integrity & Cycle Warnings** | `LOW` | `PASS` | Warnings for cyclic dependencies, malformed blocks, or unparseable attributes. |

---

## GitHub Actions CI/CD Integration

Embed the automated gate directly into your GitHub pull request workflows (`.github/workflows/terraform_blast_radius.yml`):

```yaml
name: Terraform Blast Radius CI Gate

on:
  pull_request:
    paths: ['terraform/**']

jobs:
  blast-radius:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v2
      - run: uv sync

      - name: Generate Terraform Plan JSON
        run: |
          terraform init
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json

      - name: Run Blast Radius Simulator Gate
        run: |
          uv run blast-radius analyze tfplan.json \
            --fail-on=review_required \
            --format=markdown \
            -o pr_comment.md

      - name: Post Sticky PR Comment
        if: always()
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          path: pr_comment.md
```

---

## Quality Metrics & Test Suite

The simulator is engineered to strict reliability and safety standards:

```text
================================ tests coverage ================================
TOTAL: 1447 statements | 94 tests passed | 92% statement coverage
Linters: Ruff Check: 0 errors | Ruff Format: 100% compliant
Frontend: TypeScript: Strict mode (0 errors) | Vite Production Bundle: 268 kB
```

To run all checks locally:
```bash
# Run pytest with missing-line coverage reports
uv run pytest --cov=blast_radius --cov-report=term-missing

# Run ruff lint and format check
uv run ruff check . && uv run ruff format --check .

# Build frontend production bundle
cd frontend && npm run build
```

---

## Repository Documentation Index

- **[Architecture & Design Specification](docs/architecture.md):** Directed DAG invariants, traversal mechanics, and explainable scoring mathematics.
- **[End-to-End Walkthrough & Verification Guide](docs/walkthrough.md):** Step-by-step tour of all 4 scenario presets across CLI, API, and Web UI.
- **[CI/CD Integration & Gating Guide](docs/ci_cd_integration.md):** CLI exit code contracts, GitHub Actions workflows, and GitLab CI examples.
- **[Live Cloud Integration Guide](docs/live_cloud_integration.md):** Read-only security model, supported AWS resources, drift detection, and offline fallbacks.
- **[Risk Rules & Scoring Specification](docs/risk_scoring_specification.md):** Mathematical formulas, weights, multipliers, and threshold tables.
- **[Terraform Plan Support Specification](docs/terraform_plan_support.md):** Supported Terraform format versions, action normalization, and fixture specifications.

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).
