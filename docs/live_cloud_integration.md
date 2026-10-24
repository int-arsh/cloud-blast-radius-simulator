# Safe Read-Only Live Cloud Integration Guide

The **Cloud Blast-Radius Simulator** includes an optional, safe live cloud state enrichment engine (`blast_radius.cloud.client.CloudEnricher`). While static Terraform plan analysis detects logical risks within the planned changeset, static plans alone cannot see:

1. **Active Live Safeguards:** Cloud-level protection mechanisms (such as RDS `DeletionProtection` or EC2 `DisableApiTermination`) that will cause `terraform apply` or destruction to abort unexpectedly.
2. **Out-of-Band Configuration Drift:** Discrepancies between the Terraform state file's `before` attributes and actual cloud configuration (e.g. storage auto-scaled manually or via AWS console).
3. **True Resource Existence & Production Tagging:** Validating whether resources targeted for deletion actually exist in the target account, and whether live resource tags designate the resource as mission-critical production.

---

## 1. Strict Read-Only Security Architecture

The live cloud integration module enforces a strict zero-mutation security invariant:

> [!IMPORTANT]
> **Strict Read-Only Enforcement:** Under NO circumstances does the simulator execute modifying cloud API calls. Terraform `apply`, `destroy`, or cloud mutation primitives (`create_*`, `modify_*`, `delete_*`, `terminate_*`, `update_*`, `put_*`) are strictly intercepted and rejected by `ReadOnlySecurityViolation` exceptions before reaching any cloud SDK client.

### Allowed API Primitives

Only idempotent, non-destructive read operations are permitted:

| API Prefix | Purpose | Examples |
| :--- | :--- | :--- |
| **`describe_*`** | Query resource metadata, statuses, and configuration flags | `rds.describe_db_instances`, `ec2.describe_instances`, `ec2.describe_instance_attribute` |
| **`get_*`** | Retrieve resource tags or identity tokens | `sts.get_caller_identity`, `s3.get_bucket_tagging` |
| **`head_*`** | Verify bucket/object existence without retrieving payload | `s3.head_bucket` |
| **`list_*`** | Enumerate resource associations | `rds.list_tags_for_resource` |

### Least-Privilege IAM Policy Recommendation

To execute live enrichment in CI/CD or locally, attach the following read-only IAM policy to your deployment or runner role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BlastRadiusReadOnlyInspection",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "rds:DescribeDBInstances",
        "rds:ListTagsForResource",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceAttribute",
        "s3:HeadBucket",
        "s3:GetBucketTagging"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 2. Supported Resource Types & Safeguard Audits

### AWS RDS Database Instances (`aws_db_instance`)
- **Inspection API:** `rds.describe_db_instances(DBInstanceIdentifier=...)`
- **Safeguard Verification:** Evaluates `DeletionProtection`. If a plan proposes `delete` or `replace` on an instance with live `DeletionProtection=True`, the simulator issues an **Active Safeguard Warning** and elevates the gate status to `REVIEW_REQUIRED`.
- **Drift Detection:** Compares plan `before` allocated storage against live `AllocatedStorage`. Flags out-of-band storage resizing.
- **Production Tag Audit:** Inspects `TagList` for keys `Environment`, `Env`, or `Stage` matching `production` or `prod`. Violations on destructive changes trigger immediate escalation.

### AWS EC2 Virtual Instances (`aws_instance`)
- **Inspection API:** `ec2.describe_instances`, `ec2.describe_instance_attribute(Attribute='disableApiTermination')`
- **Safeguard Verification:** Verifies `DisableApiTermination`. If an instance is slated for destruction while live termination protection is active, AWS will reject the API call during apply.
- **State Check:** Confirms whether the instance is currently running, stopped, or already terminated.

### AWS S3 Storage Buckets (`aws_s3_bucket`)
- **Inspection API:** `s3.head_bucket`, `s3.get_bucket_tagging`
- **Safeguard Verification:** Confirms bucket existence in target account.
- **Production Tag Audit:** Checks live bucket tags to confirm whether the bucket holds live production assets.

### Generic / Fallback Resources
- For resource types without dedicated cloud inspectors, the enricher records an unverified state (`provenance="aws_api(generic_unsupported)"`), ensuring that lack of specialized inspector coverage never blocks analysis.

---

## 3. Offline Simulation & Graceful Degradation

If the simulator is run in an air-gapped CI runner, developer sandbox without AWS credentials, or when SSO sessions have expired:

1. **Zero Hard Crashes:** The simulator catches authentication exceptions gracefully and switches to `offline_unauthenticated` provenance.
2. **Deterministic Baseline Intact:** Core dependency graph generation, downstream blast radius calculation, and deterministic safety rules (`RULE-001` through `RULE-008`) continue to execute with 100% fidelity.
3. **Audit Trail:** The report explicitly flags `authenticated=False` so reviewers know live cloud inspection was not performed.

---

## 4. CLI Usage & Flags

Enable live AWS inspection via the `--enrich-aws` flag:

```bash
# Basic live AWS enrichment (uses default AWS credentials / IAM role)
blast-radius analyze tfplan.json --enrich-aws

# Specify target region and AWS SSO profile
blast-radius analyze tfplan.json --enrich-aws --aws-region=us-east-1 --aws-profile=production2

# Generate Markdown PR report with live cloud safeguards section
blast-radius analyze tfplan.json --enrich-aws --format=markdown -o pr_comment.md
```

### CLI Terminal Output Sample

```text
========================================================================
  CLOUD BLAST-RADIUS SIMULATION  |  Engine v0.1.0
========================================================================
 Gate Status       : [ REVIEW_REQUIRED ]
 Risk Score        : 64.0/100.0
 Decision Reason   : Live cloud safeguards active: deletion/termination protection enabled on resources slated for destroy/replacement.
------------------------------------------------------------------------
 Total Resources   : 4
 Planned Changes   : 1 ({'delete': 1})
 Impacted Nodes    : 2 (Direct: 2, Transitive: 0)
 Graph Cycles      : 0
------------------------------------------------------------------------
 Findings (1 safety rule violations):
   [HIGH] RULE-002: Destructive Change with Active Dependents
          Target  : aws_db_instance.primary
          Remedy  : Safely migrate or decouple 2 downstream dependents before deleting.
------------------------------------------------------------------------
 Live AWS Cloud    : Authenticated (Region: us-east-1)
 Resources Checked : 1 (Existing: 1, Missing: 0, Drift: 0)
 Active Safeguards :
   [SAFEGUARD] Active Safeguard: 'aws_db_instance.primary' has DeletionProtection=True in live cloud; terraform destroy/replace will be rejected by AWS.
------------------------------------------------------------------------
```

---

## 5. API Usage

The FastAPI backend supports live cloud inspection through the optional `enrich_aws` query parameter:

### Endpoint: `POST /api/v1/analyze?enrich_aws=true`

```bash
curl -X POST "http://localhost:8000/api/v1/analyze?enrich_aws=true" \
  -H "Content-Type: application/json" \
  --data-binary @tfplan.json
```

The response includes the complete `cloud_enrichment` block:

```json
{
  "analysis_id": "sim-8f92a10c3b4e",
  "decision_status": "review_required",
  "risk_score": 64.0,
  "cloud_enrichment": {
    "provider": "aws",
    "authenticated": true,
    "region": "us-east-1",
    "resources_checked": 1,
    "resources_existing": 1,
    "resources_missing": 0,
    "drift_count": 0,
    "protection_warnings": [
      "Active Safeguard: 'aws_db_instance.primary' has DeletionProtection=True in live cloud; terraform destroy/replace will be rejected by AWS."
    ],
    "production_violations": [],
    "resource_states": {
      "aws_db_instance.primary": {
        "address": "aws_db_instance.primary",
        "resource_type": "aws_db_instance",
        "resource_id": "primary-postgres",
        "exists_in_cloud": true,
        "tags": {
          "Environment": "production"
        },
        "protection_flags": {
          "deletion_protection": true
        },
        "drift_detected": false,
        "is_production_flagged": true,
        "provenance": "aws_api(rds.describe_db_instances)"
      }
    }
  }
}
```
