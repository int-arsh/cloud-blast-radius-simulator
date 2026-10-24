# Cloud Blast-Radius Simulator: System Architecture & Design Specification

The **Cloud Blast-Radius Simulator** is a deterministic, rule-based reliability and security engine for cloud infrastructure changes. It parses proposed changes (Terraform plan JSON) before deployment, models their dependency topology, detects destructive and cascading failure scenarios, calculates explainable risk scores, and gates CI/CD pipelines to prevent outages.

---

## 1. High-Level Architectural Pipeline

The simulator operates as a strictly sequential, eight-stage analysis pipeline:

```text
[ Raw Terraform Plan JSON ]
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

## 2. Dependency Graph Modeling Convention

### The Directed Dependency Invariant

The simulator models infrastructure relationships as a directed graph G = (V, E) using NetworkX:
- **Nodes (V):** Cloud resources identified by their canonical Terraform address (e.g., `aws_db_instance.primary`).
- **Edges (E):** Directed dependency relationships.

> [!IMPORTANT]
> **Directional Convention:** An edge `A → B` strictly denotes that **Resource A depends on Resource B**.
> For example: `aws_ecs_service.api → aws_db_instance.primary`

### Traversal Semantics for Blast Radius

When a target resource R is modified or destroyed:
1. **Direct Blast Radius:** All immediate dependents that rely directly on R (in NetworkX: `G.predecessors(R)`).
2. **Transitive Blast Radius:** All cascaded dependents reachable by tracing dependency paths backward (in NetworkX: `nx.ancestors(G, R)`).
3. **Shortest Failure Path:** Computed via BFS (`nx.shortest_path(G, dependent, target)`) to explain the exact chain of causality.
4. **Zero-Hallucination Guarantee:** Edges are constructed strictly from explicit Terraform references (`depends_on`, resource attribute references, and module inputs). No edges are inferred from mere string similarity.

---

## 3. Deterministic Safety Rule Catalog

The rule catalog evaluates every proposed change against immutable infrastructure reliability and security policies:

| Rule ID | Rule Name | Default Severity | Trigger Condition |
| :--- | :--- | :---: | :--- |
| **`RULE-001`** | Critical Resource Deletion | **CRITICAL** | Target address is designated as mission-critical and slated for `delete` or `replace`. |
| **`RULE-002`** | Destructive Change with Dependents | **HIGH** | Slated for `delete` with ≥ 1 active downstream dependent resources. |
| **`RULE-003`** | In-Place Replacement of Foundational Tier | **HIGH** | Foundational resource (VPC, Subnet, DB) replaced in-place while depended on by compute/ingress tiers. |
| **`RULE-004`** | High-Velocity Destructive Actions | **HIGH** | Plan proposes ≥ 3 simultaneous destructive changes across decoupled services. |
| **`RULE-005`** | Live Safeguard Removal | **HIGH** | Plan explicitly drops `deletion_protection`, `prevent_destroy`, or `disable_api_termination`. |
| **`RULE-006`** | Sensitive Access Security Group Modification | **MEDIUM** | Ingress rule opening port `22` (SSH), `3389` (RDP), or database ports to `0.0.0.0/0`. |
| **`RULE-007`** | Uncontained Blast Radius | **MEDIUM** | Single change impacts > 50% of all known resources in the state topology. |
| **`RULE-008`** | Plan Integrity & Cyclic Dependency Warnings | **LOW** | Malformed blocks, unparseable attributes, or circular dependencies detected. |

---

## 4. Explainable Risk Scoring Formulation

The risk score is a deterministic, explainable float in the range [0.0, 100.0]:

```text
Risk Score = min(100.0, round(Base Score * Blast Radius Multiplier * Confidence Factor, 1))
```

### 1. Base Score
Computed from the highest severity rule findings:
- `CRITICAL` finding: **80.0** base points
- `HIGH` finding: **20.0** base points (additive up to 60.0 for multiple findings)
- `MEDIUM` finding: **5.0** base points
- `LOW` finding: **1.0** base point

### 2. Blast Radius Multiplier
Scales based on the count of unique downstream impacted resources:
- 0 impacted resources: **1.0x**
- 1–2 impacted resources: **1.3x**
- 3–5 impacted resources: **1.6x**
- 6+ impacted resources: **2.0x**

### 3. Confidence Factor
Weights the calculation based on evidence fidelity:
- Verified explicit references: **1.0x**
- Inferred or incomplete references: **0.8x**

---

## 5. Safe Read-Only Live Cloud Enrichment

The `CloudEnricher` module communicates with AWS via boto3 using strict read-only primitives:
- **Method Whitelist:** Only methods prefixed with `describe_*`, `get_*`, `list_*`, or `head_*` are permitted.
- **Mutation Rejection:** Any call matching `create_*`, `modify_*`, `delete_*`, `terminate_*`, `update_*`, or `put_*` raises `ReadOnlySecurityViolation`.
- **Live Audits:** Inspects active RDS `DeletionProtection`, EC2 `DisableApiTermination`, out-of-band storage drift, and `Environment=production` tags.
- **Offline Fallback:** If credentials are unconfigured or expired, gracefully continues with `authenticated=False` without failing analysis.

---

## 6. Threat Model & Security Controls

1. **Secret & Credential Redaction:**
   - Pre-ingestion sanitizer intercepts and redacts AWS access keys (`AKIA...`), bearer tokens, and private keys (`BEGIN PRIVATE KEY`) in logs and exported JSON reports.
2. **Denial of Service Prevention:**
   - Ingestion enforces a strict 10 MB payload ceiling (`HTTP 413 Content Too Large`).
   - NetworkX cycle detection prevents infinite loops during graph traversal.
3. **Data Integrity:**
   - Strict Pydantic v2 validation ensures every output field conforms to declared schema.
