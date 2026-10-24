# CI/CD Pipeline Integration & Policy Gating Guide

The **Cloud Blast-Radius Simulator** acts as an automated, deterministic security and reliability gate in Continuous Integration / Continuous Deployment (CI/CD) pipelines. By analyzing proposed Terraform plan changes (`terraform show -json tfplan.binary`) prior to `terraform apply`, teams can prevent accidental data destruction, cascading outages, and unreviewed security group exposure.

---

## 1. CLI Reference & Exit Code Protocol

The `blast-radius` CLI provides automated evaluation with predictable exit codes designed for shell scripting and CI orchestrators.

### Exit Codes

| Exit Code | Name | Condition | CI Orchestrator Behavior |
| :---: | :--- | :--- | :--- |
| **`0`** | `PASS` | Plan risk score is within `--max-score` threshold and no rule breaches match `--fail-on`. | Step passes; pipeline proceeds to deployment. |
| **`1`** | `GATE_FAILED` | Simulation evaluated to `BLOCKED` (or `REVIEW_REQUIRED` if `--fail-on=review_required`), or score exceeded `--max-score`. | Step fails; pipeline halts and blocks merge / deployment. |
| **`2`** | `INPUT_ERROR` | Missing plan file, oversized payload (>10 MB), unparseable JSON, or unsupported format. | Step errors; highlights syntax or configuration failure. |

---

### Command Syntax

```bash
blast-radius analyze <path_to_plan.json> [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--fail-on` | `blocked` \| `review_required` \| `never` | `blocked` | Gate failure sensitivity. `blocked` halts only on CRITICAL findings or score $\ge 80$. `review_required` halts on any HIGH severity finding or downstream impact. `never` always returns `0` (report-only mode). |
| `--max-score` | `float` | `None` | Explicit maximum allowable risk score (0.0 to 100.0). Breaching triggers exit `1`. |
| `--critical` | `string` | `[]` | Designate specific resource addresses as critical (e.g. `--critical aws_db_instance.primary`). Modifying or deleting these triggers `RULE-001` (CRITICAL / BLOCKED). |
| `--format` | `summary` \| `markdown` \| `json` | `summary` | Output format. `summary` emits colored ANSI terminal output. `markdown` emits a full PR comment. `json` emits sanitized structured JSON. |
| `-o`, `--output` | `string` | `None` | Path to file where generated report should be written (e.g. `--output=pr_comment.md`). |
| `-q`, `--quiet` | `flag` | `False` | Suppresses stdout output (ideal when generating file artifacts in CI). |

---

## 2. GitHub Actions Integration

### Automated Sticky PR Comment & Blocking Gate

Add `.github/workflows/terraform_blast_radius.yml` to your repository:

```yaml
name: Terraform Blast-Radius Simulation Gate

on:
  pull_request:
    paths:
      - "terraform/**"
      - "*.tf"

permissions:
  contents: read
  pull-requests: write

jobs:
  simulate-and-gate:
    name: Blast-Radius Simulation Gate
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.5.7"

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Cloud Blast-Radius Simulator
        run: |
          pip install git+https://github.com/charlesandcolvard/cloud-blast-radius-simulator.git

      - name: Generate Terraform Plan JSON
        run: |
          terraform init -backend=false
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json

      - name: Run Blast-Radius Simulator
        id: blast_radius
        run: |
          blast-radius analyze tfplan.json \
            --format=markdown \
            --output=blast-radius-report.md \
            --fail-on=blocked \
            --max-score=75.0 \
            --critical aws_db_instance.primary \
            --critical aws_route53_zone.production
        continue-on-error: true

      - name: Post or Update Sticky PR Comment
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
            const commentFile = 'blast-radius-report.md';
            if (!fs.existsSync(commentFile)) return;
            
            const body = fs.readFileSync(commentFile, 'utf8');
            const botMarker = '<!-- blast-radius-simulation-comment -->';
            const fullBody = `${botMarker}\n${body}`;

            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
            });

            const existingComment = comments.find(c => c.body.includes(botMarker));
            if (existingComment) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: existingComment.id,
                body: fullBody,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body: fullBody,
              });
            }

      - name: Enforce Gate Failure
        if: steps.blast_radius.outcome != 'success'
        run: |
          echo "CI Gating Violation: Plan exceeds blast-radius risk thresholds."
          exit 1
```

---

## 3. GitLab CI Integration

In `.gitlab-ci.yml`, run simulation within your Terraform planning stage:

```yaml
stages:
  - plan
  - simulate
  - apply

simulate_blast_radius:
  stage: simulate
  image: python:3.13-slim
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  before_script:
    - pip install cloud-blast-radius-simulator
  script:
    - blast-radius analyze tfplan.json --format=markdown --output=report.md --fail-on=blocked
  after_script:
    - |
      # Post report to GitLab Merge Request Notes API
      curl --request POST \
        --header "PRIVATE-TOKEN: ${GITLAB_API_TOKEN}" \
        --form "body=<report.md" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/merge_requests/${CI_MERGE_REQUEST_IID}/notes"
  artifacts:
    paths:
      - report.md
    expire_in: 7 days
```

---

## 4. Pre-commit Hook Integration

To guard developer environments before commits are pushed, configure `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: blast-radius-check
        name: Cloud Blast-Radius Pre-Commit Gating
        entry: blast-radius analyze
        language: system
        files: '.*tfplan\.json$'
        args: ["--fail-on=review_required", "--max-score=30.0"]
```

---

## 5. Enterprise Environment Policy Matrix

Teams should tune gating thresholds across environments:

| Environment | `--fail-on` | `--max-score` | Description |
| :--- | :---: | :---: | :--- |
| **Dev / Sandbox** | `never` | `None` | Diagnostic reporting only. Zero blocker on active prototyping. |
| **Staging / QA** | `blocked` | `75.0` | Prevents destructive drops while permitting active schema iterations. |
| **Production** | `review_required` | `30.0` | Strict zero-disruption gate. Any destructive change or active dependent cascade requires explicit change advisory sign-off. |
