import React from 'react';
import { X, Layers, ArrowRight, Cpu } from 'lucide-react';
import type { FullAnalysisReport, NormalizedAction } from '../types';

interface ResourceInspectorProps {
  report: FullAnalysisReport;
  selectedAddress: string | null;
  onClose: () => void;
  onSelectAddress: (address: string) => void;
}

export const ResourceInspector: React.FC<ResourceInspectorProps> = ({
  report,
  selectedAddress,
  onClose,
  onSelectAddress,
}) => {
  if (!selectedAddress) {
    return (
      <div className="glass-panel inspector-panel">
        <div className="inspector-header">
          <div className="section-title">
            <Cpu size={18} color="#6366f1" />
            <span>Resource Inspector</span>
          </div>
        </div>
        <div className="inspector-empty">
          <Layers size={36} color="#475569" />
          <p style={{ fontWeight: 600, color: '#94a3b8' }}>No Resource Selected</p>
          <p style={{ fontSize: '0.8rem', color: '#64748b' }}>
            Click any resource node on the dependency graph or any item in the findings table to inspect its blast propagation chain and safety findings.
          </p>
        </div>
      </div>
    );
  }

  // Find node metadata
  const node = report.nodes.find((n) => n.address === selectedAddress);
  const action: NormalizedAction = node?.action || 'no-op';

  // Find blast radius entry if this resource is changing
  const blastRadius = report.impact_summary.resource_blast_radii.find(
    (r) => r.resource_address === selectedAddress
  );

  // Find incoming impacts if this resource is an impacted dependent
  const triggeredImpacts = report.impact_summary.resource_blast_radii.flatMap((r) =>
    r.impacted_resources
      .filter((imp) => imp.address === selectedAddress)
      .map((imp) => ({ root: r.resource_address, impact: imp }))
  );

  // Find safety findings targeting this resource
  const relatedFindings = report.findings.filter(
    (f) => f.resource_address === selectedAddress
  );

  // Direct dependencies (what this node depends on)
  const outgoingDependencies = report.edges.filter((e) => e.source === selectedAddress);
  // Direct dependents (what depends on this node)
  const incomingDependents = report.edges.filter((e) => e.target === selectedAddress);

  return (
    <div className="glass-panel inspector-panel">
      <div className="inspector-header">
        <div className="section-title">
          <Cpu size={18} color="#6366f1" />
          <span>Resource Inspector</span>
        </div>
        <button
          type="button"
          className="btn-icon"
          onClick={onClose}
          title="Close inspector"
        >
          <X size={16} />
        </button>
      </div>

      <div className="inspector-body">
        {/* Resource Header */}
        <div className="inspector-prop-group">
          <span className="inspector-prop-label">Resource Address</span>
          <div className="inspector-prop-val" style={{ fontWeight: 700, color: '#f8fafc' }}>
            {selectedAddress}
          </div>
        </div>

        {/* Action & Type */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div className="inspector-prop-group">
            <span className="inspector-prop-label">Lifecycle Action</span>
            <div>
              <span className={`action-pill ${action}`}>{action.toUpperCase()}</span>
            </div>
          </div>

          <div className="inspector-prop-group">
            <span className="inspector-prop-label">Resource Type</span>
            <div className="inspector-prop-val" style={{ fontSize: '0.75rem' }}>
              {node?.resource_type || selectedAddress.split('.')[0]}
            </div>
          </div>
        </div>

        {/* Downstream Blast Radius Scope (if changing) */}
        {blastRadius && (
          <div className="inspector-prop-group">
            <span className="inspector-prop-label" style={{ color: '#ef4444' }}>
              ⚡ Downstream Blast Radius ({blastRadius.total_impacted_count} impacted)
            </span>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '8px' }}>
              {blastRadius.summary}
            </div>

            {blastRadius.impacted_resources.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {blastRadius.impacted_resources.map((imp) => (
                  <div
                    key={imp.address}
                    style={{
                      background: 'rgba(0, 0, 0, 0.4)',
                      padding: '10px',
                      borderRadius: '6px',
                      border: '1px solid rgba(239, 68, 68, 0.2)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span
                        style={{
                          fontSize: '0.8rem',
                          fontWeight: 700,
                          cursor: 'pointer',
                          color: '#38bdf8',
                        }}
                        onClick={() => onSelectAddress(imp.address)}
                        title="Click to inspect this dependent"
                      >
                        {imp.address}
                      </span>
                      <span
                        style={{
                          fontSize: '0.65rem',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: imp.impact_type === 'direct' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: imp.impact_type === 'direct' ? '#ef4444' : '#f59e0b',
                        }}
                      >
                        {imp.impact_type.toUpperCase()} ({imp.path_length} hop{imp.path_length > 1 ? 's' : ''})
                      </span>
                    </div>

                    {/* Propagation Path */}
                    <div
                      style={{
                        marginTop: '6px',
                        fontSize: '0.72rem',
                        fontFamily: 'var(--font-mono)',
                        color: '#94a3b8',
                        display: 'flex',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '4px',
                      }}
                    >
                      {imp.shortest_path.map((step, idx) => (
                        <React.Fragment key={idx}>
                          <span>{step.split('.')[1] || step}</span>
                          {idx < imp.shortest_path.length - 1 && (
                            <ArrowRight size={10} color="#ef4444" />
                          )}
                        </React.Fragment>
                      ))}
                    </div>

                    <div style={{ marginTop: '6px', fontSize: '0.75rem', color: '#cbd5e1' }}>
                      {imp.potential_failure_scenario}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Upstream Cause (if this node is impacted by an upstream change) */}
        {triggeredImpacts.length > 0 && !blastRadius && (
          <div className="inspector-prop-group">
            <span className="inspector-prop-label" style={{ color: '#f59e0b' }}>
              ⚠️ Downstream Impact Triggered by Root Cause
            </span>
            {triggeredImpacts.map(({ root, impact }, idx) => (
              <div
                key={idx}
                style={{
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  padding: '10px',
                  borderRadius: '6px',
                }}
              >
                <div style={{ fontSize: '0.78rem', color: '#f8fafc' }}>
                  Triggered by:{' '}
                  <strong
                    style={{ color: '#38bdf8', cursor: 'pointer' }}
                    onClick={() => onSelectAddress(root)}
                  >
                    {root}
                  </strong>{' '}
                  ({impact.triggering_action})
                </div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '4px' }}>
                  {impact.explanation}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Safety Findings for this resource */}
        {relatedFindings.length > 0 && (
          <div className="inspector-prop-group">
            <span className="inspector-prop-label" style={{ color: '#ef4444' }}>
              Safety Violations ({relatedFindings.length})
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {relatedFindings.map((finding) => (
                <div
                  key={finding.finding_id}
                  style={{
                    background: 'rgba(239, 68, 68, 0.12)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    borderRadius: '6px',
                    padding: '10px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: '#ef4444', fontWeight: 700 }}>
                      {finding.rule_id}
                    </span>
                    <span className={`severity-badge ${finding.severity}`}>{finding.severity}</span>
                  </div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f8fafc', marginTop: '4px' }}>
                    {finding.title}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#cbd5e1', marginTop: '4px' }}>
                    {finding.description}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#a5b4fc', marginTop: '6px' }}>
                    💡 {finding.remediation}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Direct Dependencies & Dependents */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div className="inspector-prop-group">
            <span className="inspector-prop-label">Depends On ({outgoingDependencies.length})</span>
            {outgoingDependencies.length === 0 ? (
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>None (Foundational)</span>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {outgoingDependencies.map((e, idx) => (
                  <span
                    key={idx}
                    style={{ fontSize: '0.75rem', color: '#38bdf8', cursor: 'pointer' }}
                    onClick={() => onSelectAddress(e.target)}
                  >
                    • {e.target}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="inspector-prop-group">
            <span className="inspector-prop-label">Dependents ({incomingDependents.length})</span>
            {incomingDependents.length === 0 ? (
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>None</span>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {incomingDependents.map((e, idx) => (
                  <span
                    key={idx}
                    style={{ fontSize: '0.75rem', color: '#38bdf8', cursor: 'pointer' }}
                    onClick={() => onSelectAddress(e.source)}
                  >
                    • {e.source}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
