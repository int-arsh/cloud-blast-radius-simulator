export type NormalizedAction =
  | 'create'
  | 'update'
  | 'delete'
  | 'replace'
  | 'read'
  | 'no-op';

export type DecisionStatus =
  | 'pass'
  | 'review_required'
  | 'blocked'
  | 'analysis_incomplete';

export type RiskSeverity =
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  | 'info';

export type ConfidenceLevel =
  | 'verified'
  | 'high'
  | 'medium'
  | 'low'
  | 'unknown';

export interface RiskFinding {
  finding_id: string;
  rule_id: string;
  title: string;
  description: string;
  severity: RiskSeverity;
  resource_address: string;
  impact_scope: string;
  remediation: string;
  evidence: string[];
}

export interface RiskScoreBreakdown {
  base_score: number;
  blast_radius_multiplier: number;
  confidence_factor: number;
  final_score: number;
  formula: string;
}

export interface ImpactedResource {
  address: string;
  resource_type: string;
  impact_type: 'direct' | 'transitive';
  triggering_resource: string;
  triggering_action: NormalizedAction;
  shortest_path: string[];
  path_length: number;
  evidence: string[];
  explanation: string;
  potential_failure_scenario: string;
  confidence: ConfidenceLevel;
  has_missing_evidence: boolean;
}

export interface ResourceBlastRadius {
  resource_address: string;
  action: NormalizedAction;
  is_destructive: boolean;
  direct_dependents_count: number;
  transitive_dependents_count: number;
  total_impacted_count: number;
  impacted_resources: ImpactedResource[];
  missing_evidence_warnings: string[];
  summary: string;
}

export interface ImpactAnalysisReport {
  total_changed_resources: number;
  total_impacted_resources: number;
  direct_impact_count: number;
  transitive_impact_count: number;
  unaffected_resource_count: number;
  resource_blast_radii: ResourceBlastRadius[];
  unique_impacted_addresses: string[];
  missing_information_warnings: string[];
  has_destructive_impact: boolean;
  metadata?: Record<string, unknown>;
}

export interface ResourceNode {
  address: string;
  resource_type: string;
  resource_name: string;
  mode: string;
  provider_name?: string | null;
  is_in_plan: boolean;
  action?: NormalizedAction | null;
  is_destructive: boolean;
  metadata?: Record<string, unknown>;
}

export interface DependencyEdge {
  source: string;
  target: string;
  evidence_category: string;
  confidence: ConfidenceLevel;
  provenance: string;
  is_direct: boolean;
}

export interface FullAnalysisReport {
  analysis_id: string;
  timestamp: string;
  engine_version: string;
  format_version: string;
  terraform_version?: string | null;
  decision_status: DecisionStatus;
  decision_reason: string;
  risk_score: number;
  score_breakdown: RiskScoreBreakdown;
  resource_counts: {
    total: number;
    changed: number;
    impacted: number;
    unaffected: number;
    [key: string]: number;
  };
  action_counts: Record<string, number>;
  dependency_counts: {
    nodes: number;
    edges: number;
    cycles: number;
    isolated: number;
    missing: number;
    [key: string]: number;
  };
  severity_counts: Record<string, number>;
  impact_summary: ImpactAnalysisReport;
  nodes: ResourceNode[];
  edges: DependencyEdge[];
  findings: RiskFinding[];
  warnings: string[];
  remediations: string[];
  metadata?: Record<string, unknown>;
}

export interface SamplePlanOption {
  id: string;
  label: string;
  description: string;
  tag: string;
  tagColor: string;
  jsonContent: string;
}
