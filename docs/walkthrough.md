# End-to-End Walkthrough & Verification Guide

This walkthrough provides a comprehensive, reproducible demonstration of the **Cloud Blast-Radius Simulator** across the Command-Line Interface (CLI), the REST API, and the Interactive Web UI.

---

## 1. Quick Verification Matrix

| Scenario | Fixture File | Lifecycle Change | Blast Radius Impact | Gate Status | Risk Score | Key Finding |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **1. Clean Additions** | `add_resource.json` | 1 Addition (`create`) | 0 Dependents | **`PASS`** | `0.0` | None (Clean Plan) |
| **2. Database Deletion** | `delete_with_dependents.json` | 1 Deletion (`delete`) | 2 Dependents | **`REVIEW_REQUIRED`** | `26.0` | `RULE-002` (Dependent API & DNS) |
| **3. Subnet Replacement** | `replace_with_dependents.json` | 1 In-Place Replace (`replace`) | 2 Dependents | **`REVIEW_REQUIRED`** | `32.0` | `RULE-003` (Foundational Tier) |
| **4. Circular Graph** | `cyclic_dependency.json` | 1 Modification (`update`) | Cycle Contained | **`PASS`** | `0.0` | `RULE-008` (Cycle Detected) |

---

## 2. CLI End-to-End Walkthrough

Run each command from the root of the repository:

### Scenario 1: Clean Infrastructure Addition (Zero Risk)
```bash
blast-radius analyze tests/fixtures/add_resource.json
```
**Expected Outcome:**
- Decision: `[ PASS ]`
- Risk Score: `0.0/100.0`
- Exit Code: `0`

### Scenario 2: High-Impact Database Deletion
```bash
blast-radius analyze tests/fixtures/delete_with_dependents.json --fail-on=review_required
```
**Expected Outcome:**
- Decision: `[ REVIEW_REQUIRED ]`
- Risk Score: `26.0/100.0`
- Exit Code: `1` (Halt CI pipeline due to active downstream dependents)
- Downstream Impacts: Direct dependents `aws_ecs_service.api` and `aws_route53_record.db`.

### Scenario 3: Mission-Critical Resource Gating
```bash
blast-radius analyze tests/fixtures/delete_with_dependents.json \
  --critical=aws_db_instance.primary \
  --fail-on=blocked
```
**Expected Outcome:**
- Decision: `[ BLOCKED ]`
- Risk Score: `100.0/100.0`
- Exit Code: `1`
- Triggered Rule: `RULE-001: Destruction of Mission-Critical Resource`

### Scenario 4: Live Read-Only AWS Cloud Inspection
```bash
blast-radius analyze tests/fixtures/delete_with_dependents.json --enrich-aws
```
**Expected Outcome:**
- Inspects target AWS account safely using only read-only primitives (`describe_*`, `get_*`).
- If credentials are offline, cleanly outputs:
  ```text
  Live AWS Cloud    : Offline / Simulation (Region: us-east-1)
  Resources Checked : 3 (Exist: 0, Missing: 0, Drift: 0)
  ```

### Scenario 5: Markdown PR Comment Generation
```bash
blast-radius analyze tests/fixtures/replace_with_dependents.json \
  --format=markdown \
  --output=pr_comment.md
```
Generates a complete, ready-to-post GitHub PR comment document with impact tables, failure scenarios, and recommended mitigations.

---

## 3. Web UI Interactive Walkthrough

Ensure services are running:
```bash
# Terminal 1: FastAPI Backend
uv run uvicorn blast_radius.api.app:app --port 8000

# Terminal 2: Vite React Frontend
cd frontend && npm run dev
```

Open your browser to: **`http://localhost:5173`**

### Steps to Test:
1. **Scenario Preset Selector:** Click the Scenario dropdown in the header and switch between:
   - *Cascading Subnet Replacement (High Risk)*
   - *Direct Database Deletion (Destructive)*
   - *Clean Infrastructure Addition (Zero Risk)*
   - *Cyclic Dependency Graph (Topology Warning)*
2. **Interactive SVG DAG Visualizer:**
   - Observe how resources slated for change are highlighted in **Amber / Red** with glowing borders.
   - Hover over nodes to highlight upstream and downstream connection edges.
   - Click any node (e.g. `aws_subnet.private_app`) to open the **Resource Inspector** side-drawer.
3. **Resource Inspector Drawer:**
   - Displays canonical address, lifecycle action badge, in-degree and out-degree connectivity, and explicit failure scenarios.
4. **Findings & Remediation Panel:**
   - Review rule violation cards with severity badges, evidence provenance, confidence ratings, and prescriptive fix steps.
5. **Custom Plan Upload:**
   - Drag and drop your own `terraform show -json` file into the upload zone to visualize custom infrastructure plans in real-time.

---

## 4. REST API Walkthrough

### Health Check
```bash
curl -s http://localhost:8000/health | jq .
```
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development"
}
```

### Analyze Plan via JSON Body
```bash
curl -s -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Content-Type: application/json" \
  --data-binary @tests/fixtures/delete_with_dependents.json | jq '{status: .decision_status, score: .risk_score, findings: .findings | length}'
```
```json
{
  "status": "review_required",
  "score": 26.0,
  "findings": 1
}
```

### Export Markdown PR Comment via API
```bash
curl -s -X POST "http://localhost:8000/api/v1/analyze/export?format=markdown" \
  -H "Content-Type: application/json" \
  --data-binary @tests/fixtures/replace_with_dependents.json
```
