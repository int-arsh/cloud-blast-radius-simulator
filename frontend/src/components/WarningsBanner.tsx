import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';

interface WarningsBannerProps {
  warnings: string[];
}

export const WarningsBanner: React.FC<WarningsBannerProps> = ({ warnings }) => {
  const [expanded, setExpanded] = useState(false);

  if (!warnings || warnings.length === 0) return null;

  return (
    <div
      style={{
        background: 'rgba(245, 158, 11, 0.1)',
        border: '1px solid rgba(245, 158, 11, 0.3)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'pointer',
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <AlertTriangle size={18} color="#f59e0b" />
          <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f59e0b' }}>
            Simulation Notice: {warnings.length} Plan Integrity / Incomplete Dependency Warning{warnings.length > 1 ? 's' : ''}
          </span>
        </div>

        <button
          type="button"
          style={{ background: 'transparent', border: 'none', color: '#f59e0b', cursor: 'pointer' }}
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {expanded && (
        <ul style={{ paddingLeft: '28px', fontSize: '0.8rem', color: '#cbd5e1', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {warnings.map((w, idx) => (
            <li key={idx}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
};
