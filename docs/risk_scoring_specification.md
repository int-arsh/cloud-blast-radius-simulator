# Deterministic Risk Rules, Scoring Model & Gating Specification

## 1. Safety Rules Catalog (Module E)

All safety rules are deterministic: identical plans evaluated with identical configurations will always yield identical findings.

| Rule ID | Rule Name | Trigger Criteria | Severity | Actionable Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **`RULE-001`** | **Critical Resource Deletion** | Proposes deletion of a resource present in `critical_resources` config or tagged `Environment=production` / `Criticality=critical`. | `CRITICAL` | Obtain change advisory board approval or preserve the resource. |
| **`RULE-002`** | **Destruction with Dependents** | Proposes deletion of a resource where `direct_dependents_count > 0`. | `HIGH` (or `CRITICAL` if direct dependents ≥ 3) | Decouple or migrate downstream dependents prior to destruction. |
| **`RULE-003`** | **Replacement with Dependents** | Proposes replacement (`replace`) of a resource with `total_impacted_count > 0`. | `HIGH` | Use `create_before_destroy = true` or plan a maintenance window. |
| **`RULE-004`** | **Multiple Destructive Actions** | Two or more resources slated for destruction (`delete` or `replace`) in one plan. | `MEDIUM` (or `HIGH` if ≥ 5) | Decompose large plans into smaller, incrementally verifiable pull requests. |
| **`RULE-005`** | **Protection Removal** | Disabling `deletion_protection` from `true` to `false` in planned changes. | `CRITICAL` | Re-enable deletion protection unless an intentional decommission is approved. |
| **`RULE-006`** | **Sensitive Access Exposure** | Security group rule opening ingress to `0.0.0.0/0`. | `HIGH` | Restrict CIDR blocks to internal VPCs or designated bastion IPs. |
| **`RULE-007`** | **Missing Dependency Evidence** | Destructive change where dependency evidence contains unmanaged or missing links. | `MEDIUM` | Inspect live infrastructure or upstream modules to verify all dependencies. |
| **`RULE-008`** | **Plan Integrity Warnings** | Structural parsing errors or unsupported Terraform action combinations. | `CRITICAL` (if plan invalid) / `MEDIUM` | Inspect plan generation pipeline and ensure Terraform CLI compatibility. |

---

## 2. Explainable Scoring Model (Module F)

The simulator employs a deterministic, transparent formula. It explicitly differentiates **Severity**, **Blast Radius**, and **Evidence Confidence**:

### A. Severity Base Score
```text
Base Score = sum(Weight(finding.severity) for finding in findings)
```

Where weights are defined as:
- `CRITICAL`: 40.0
- `HIGH`: 20.0
- `MEDIUM`: 10.0
- `LOW`: 3.0
- `INFO`: 0.0

### B. Blast Radius Multiplier
Scales the base score based on total unique downstream impacted resources:
```text
Multiplier = min(2.5, 1.0 + (total_impacted_resources * 0.15))
```

### C. Evidence Confidence Factor
Averages confidence multipliers across findings (1.0 for `VERIFIED`, 0.85 for `MEDIUM`, 0.70 for `LOW`).

### D. Final Bounded Score
```text
Final Score = min(100.0, max(0.0, round(Base Score * Multiplier * Confidence Factor, 1)))
```

---

## 3. Decision Statuses & CI/CD Gating Thresholds

- **`BLOCKED`**:
  - Any finding with `CRITICAL` severity (e.g. critical resource deletion, protection removal, invalid plan), **OR**
  - Final risk score ≥ 80.0.
- **`REVIEW_REQUIRED`**:
  - Any finding with `HIGH` severity (e.g. security group open to 0.0.0.0/0, resource replacement impacting dependents), **OR**
  - Destructive change with downstream dependents, **OR**
  - Final risk score ≥ 30.0.
- **`PASS`**:
  - Safe to apply. No critical or high risks, score < 30.0.
- **`ANALYSIS_INCOMPLETE`**:
  - Top-level parsing errors, malformed JSON, or unanalyzable plan structure.

---

## 4. Limitations: False Positives & False Negatives

### False Positive Limitations
1. **Unused Connections:** A Terraform configuration may declare an explicit reference (e.g. `depends_on = [aws_db_instance.primary]`) for sequencing purposes even if application traffic does not actively flow over it at runtime. The simulator will report downstream impact based on the declared dependency.
2. **Transient Failover:** The simulator reports potential disruption when a database is deleted or replaced. If the database has multi-AZ active-passive automatic failover, actual application outage duration may be minimal.
3. **Overlapping Rules:** A destructive change with multiple dependents may trigger both `RULE-002` (Destruction with Dependents) and `RULE-004` (Multiple Destructive Actions).

### False Negative Limitations
1. **Application-Level Dynamic DNS:** Dependencies established entirely in application runtime code (e.g., hardcoded IP or private DNS queried dynamically) that are not declared in Terraform configuration expressions cannot be parsed from the plan file alone.
2. **External Cloud Resources:** Resources provisioned in separate Terraform states, AWS accounts, or manual console clicks that consume this infrastructure without explicit Terraform state references will not appear in the static graph.
3. **No Downtime Guarantee:** The simulator never guarantees that an infrastructure change with a low score will not cause an outage. Low scores simply indicate that no safety rules were violated based on available evidence.
