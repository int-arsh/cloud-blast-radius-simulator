import React from 'react';
import { ShieldCheck, AlertTriangle, ShieldAlert, HelpCircle, Activity, GitCommit, Network } from 'lucide-react';
import type { FullAnalysisReport, DecisionStatus } from '../types';

interface SummaryCardsProps {
  report: FullAnalysisReport;
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({ report }) => {
  const getDecisionDetails = (status: DecisionStatus) => {
    switch (status) {
      case 'pass':
        return {
          label: 'PASS',
          className: 'pass',
          icon: <ShieldCheck size={20} color="#10b981" />,
        };
      case 'review_required':
        return {
          label: 'REVIEW REQUIRED',
          className: 'review_required',
          icon: <AlertTriangle size={20} color="#f59e0b" />,
        };
      case 'blocked':
        return {
          label: 'BLOCKED',
          className: 'blocked',
          icon: <ShieldAlert size={20} color="#ef4444" />,
        };
      case 'analysis_incomplete':
      default:
        return {
          label: 'INCOMPLETE',
          className: 'analysis_incomplete',
          icon: <HelpCircle size={20} color="#64748b" />,
        };
    }
  };

  const decision = getDecisionDetails(report.decision_status);

  // Determine score color
  const getScoreColor = (score: number) => {
    if (score >= 80) return '#ef4444';
    if (score >= 30) return '#f59e0b';
    return '#10b981';
  };

  const scoreColor = getScoreColor(report.risk_score);

  return (
    <div className="summary-grid">
      {/* 1. Gate Status Card */}
      <div className="glass-panel summary-card">
        <div className="summary-card-header">
          <span className="card-title">CI/CD Gate Decision</span>
          <div className="card-icon">{decision.icon}</div>
        </div>

        <div className="decision-badge-container">
          <div className={`decision-badge ${decision.className}`}>
            {decision.icon}
            <span>{decision.label}</span>
          </div>
        </div>

        <div className="card-footer" style={{ marginTop: '14px', fontSize: '0.78rem' }}>
          {report.decision_reason}
        </div>
      </div>

      {/* 2. Blast Radius Risk Score */}
      <div className="glass-panel summary-card">
        <div className="summary-card-header">
          <span className="card-title">Blast-Radius Score</span>
          <div className="card-icon">
            <Activity size={18} color={scoreColor} />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span className="card-value" style={{ color: scoreColor }}>
            {report.risk_score.toFixed(1)}
          </span>
          <span style={{ fontSize: '1rem', color: '#64748b', fontWeight: 600 }}>/ 100.0</span>
        </div>

        <div className="score-bar-bg">
          <div
            className="score-bar-fill"
            style={{
              width: `${Math.min(100, Math.max(0, report.risk_score))}%`,
              backgroundColor: scoreColor,
              boxShadow: `0 0 10px ${scoreColor}88`,
            }}
          />
        </div>

        <div className="card-footer" style={{ justifyContent: 'space-between' }}>
          <span>Multiplier: {report.score_breakdown.blast_radius_multiplier.toFixed(1)}x</span>
          <span>Confidence: {(report.score_breakdown.confidence_factor * 100).toFixed(0)}%</span>
        </div>
      </div>

      {/* 3. Planned Changes */}
      <div className="glass-panel summary-card">
        <div className="summary-card-header">
          <span className="card-title">Planned Resource Changes</span>
          <div className="card-icon">
            <GitCommit size={18} color="#6366f1" />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span className="card-value">{report.resource_counts.changed ?? 0}</span>
          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>
            of {report.resource_counts.total ?? 0} resources
          </span>
        </div>

        <div style={{ display: 'flex', gap: '6px', marginTop: '10px', flexWrap: 'wrap' }}>
          {report.action_counts.create ? (
            <span className="action-pill create">+{report.action_counts.create} create</span>
          ) : null}
          {report.action_counts.delete ? (
            <span className="action-pill delete">-{report.action_counts.delete} delete</span>
          ) : null}
          {report.action_counts.replace ? (
            <span className="action-pill replace">~{report.action_counts.replace} replace</span>
          ) : null}
          {report.action_counts.update ? (
            <span className="action-pill update">*{report.action_counts.update} update</span>
          ) : null}
        </div>

        <div className="card-footer">
          <span>Unaffected in plan: {report.resource_counts.unaffected ?? 0}</span>
        </div>
      </div>

      {/* 4. Downstream Impacted Dependents */}
      <div className="glass-panel summary-card">
        <div className="summary-card-header">
          <span className="card-title">Impacted Dependents</span>
          <div className="card-icon">
            <Network size={18} color="#f59e0b" />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span className="card-value" style={{ color: report.impact_summary.total_impacted_resources > 0 ? '#f59e0b' : '#f8fafc' }}>
            {report.impact_summary.total_impacted_resources}
          </span>
          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>downstream nodes</span>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            Direct: <strong style={{ color: '#f8fafc' }}>{report.impact_summary.direct_impact_count}</strong>
          </span>
          <span style={{ color: '#475569' }}>•</span>
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            Transitive: <strong style={{ color: '#f8fafc' }}>{report.impact_summary.transitive_impact_count}</strong>
          </span>
        </div>

        <div className="card-footer">
          <span>
            {report.impact_summary.has_destructive_impact
              ? '⚠️ Destructive downstream cascade detected'
              : 'Zero destructive downstream cascade'}
          </span>
        </div>
      </div>
    </div>
  );
};
