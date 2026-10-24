# Cloud Blast-Radius Simulator

A deterministic cloud infrastructure change blast radius and risk analyzer.

## Overview

Cloud Blast-Radius Simulator analyzes proposed infrastructure changes (e.g., Terraform plan JSON) and predicts potential downstream impact before deployment.

### Key Capabilities
- **Deterministic Risk Analysis**: Rule-based evaluation without opaque LLM decisions overriding safety policies.
- **Dependency Graph Modeling**: Builds directed dependency graphs with strict provenance (`terraform_reference`, `inferred`, `unknown`).
- **Blast Radius & Downstream Traversal**: Identifies direct and transitive dependents affected by destructive or modifying actions.
- **Evidence-Backed Findings**: Every finding links affected resources, change actions, triggering rules, confidence, and remediations.
- **Safe Execution**: Read-only evaluation — never executes `terraform apply` or alters live cloud resources.

For details on supported plan structures, see [Terraform Plan Support Specification](docs/terraform_plan_support.md).
For safety rules, scoring formulas, and CI/CD thresholds, see [Risk Rules & Scoring Specification](docs/risk_scoring_specification.md).

## Quickstart

### Prerequisites
- Python >= 3.12 (CPython 3.13 supported)
- [uv](https://docs.astral.sh/uv/) or standard `pip` / `venv`
- Node.js >= 20 (for frontend)

### Installation
```bash
# Create virtual environment
uv venv --python 3.13 .venv
source .venv/bin/activate

# Install dependencies in editable mode
uv pip install -e ".[dev]"
```

### Running Tests and Linters
```bash
# Run test suite
pytest

# Run linter checks
ruff check .
```

### Starting the API Service
```bash
uvicorn blast_radius.api.app:app --reload --port 8000
```
Visit `http://localhost:8000/docs` for the interactive OpenAPI documentation or `http://localhost:8000/health` for service health.
