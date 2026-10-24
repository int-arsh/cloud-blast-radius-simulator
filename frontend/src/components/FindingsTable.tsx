import React, { useState } from 'react';
import { ShieldAlert, CheckCircle2, Search, Lightbulb, ExternalLink } from 'lucide-react';
import type { RiskFinding } from '../types';

interface FindingsTableProps {
  findings: RiskFinding[];
  onSelectResource: (address: string) => void;
}

export const FindingsTable: React.FC<FindingsTableProps> = ({
  findings,
  onSelectResource,
}) => {
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const severityCounts = {
    all: findings.length,
    critical: findings.filter((f) => f.severity === 'critical').length,
    high: findings.filter((f) => f.severity === 'high').length,
    medium: findings.filter((f) => f.severity === 'medium').length,
    low: findings.filter((f) => f.severity === 'low').length,
  };

  const filteredFindings = findings.filter((f) => {
    const matchesSeverity =
      selectedSeverity === 'all' || f.severity === selectedSeverity;
    const matchesSearch =
      searchQuery === '' ||
      f.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.rule_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.resource_address.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSeverity && matchesSearch;
  });

  return (
    <section className="glass-panel findings-section">
      <div className="findings-toolbar">
        <div className="section-title">
          <ShieldAlert size={20} color="#ef4444" />
          <span>Safety Findings & Rule Violations</span>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            ({filteredFindings.length} of {findings.length})
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {/* Severity Filter Tabs */}
          <div className="filter-tabs">
            {(['all', 'critical', 'high', 'medium', 'low'] as const).map((sev) => (
              <button
                key={sev}
                type="button"
                className={`filter-tab ${selectedSeverity === sev ? 'active' : ''}`}
                onClick={() => setSelectedSeverity(sev)}
              >
                {sev.toUpperCase()} ({severityCounts[sev]})
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={14} color="#64748b" style={{ position: 'absolute', left: '10px' }} />
            <input
              type="text"
              placeholder="Filter findings..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="graph-search-input"
              style={{ paddingLeft: '30px', width: '200px' }}
            />
          </div>
        </div>
      </div>

      {findings.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: '#10b981' }}>
          <CheckCircle2 size={40} style={{ margin: '0 auto 10px auto' }} />
          <h4 style={{ fontWeight: 700 }}>Clean Simulation — No Risk Violations Detected</h4>
          <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '4px' }}>
            All safety rules passed with zero detected destructive hazards or unprotected resource disruptions.
          </p>
        </div>
      ) : filteredFindings.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '30px 20px', color: '#64748b' }}>
          <p>No findings matching the selected filters.</p>
        </div>
      ) : (
        <div className="findings-list">
          {filteredFindings.map((finding) => (
            <div
              key={finding.finding_id}
              className={`finding-card ${finding.severity}`}
            >
              <div className="finding-card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className={`severity-badge ${finding.severity}`}>
                    {finding.severity}
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: '#94a3b8', fontWeight: 700 }}>
                    {finding.rule_id}
                  </span>
                  <span className="finding-title">{finding.title}</span>
                </div>

                <button
                  type="button"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#38bdf8',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                  onClick={() => onSelectResource(finding.resource_address)}
                  title="Highlight resource on dependency graph"
                >
                  <span>{finding.resource_address}</span>
                  <ExternalLink size={12} />
                </button>
              </div>

              <div className="finding-desc">{finding.description}</div>

              {finding.impact_scope && (
                <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>
                  <strong>Impact Scope:</strong> {finding.impact_scope}
                </div>
              )}

              <div className="finding-remediation-box">
                <Lightbulb size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
                <span>
                  <strong>Remediation:</strong> {finding.remediation}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
