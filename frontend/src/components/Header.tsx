import React from 'react';
import { ShieldAlert, Download, Copy, Check } from 'lucide-react';

interface HeaderProps {
  engineVersion: string;
  isBackendOnline: boolean;
  onExportMarkdown: () => void;
  onExportJson: () => void;
  onCopyMarkdown: () => void;
  copied: boolean;
  hasReport: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  engineVersion,
  isBackendOnline,
  onExportMarkdown,
  onExportJson,
  onCopyMarkdown,
  copied,
  hasReport,
}) => {
  return (
    <header className="app-header">
      <div className="header-inner">
        <div className="brand-section">
          <div className="brand-logo-icon">
            <ShieldAlert size={22} />
          </div>
          <div>
            <h1 className="brand-title">Cloud Blast-Radius Simulator</h1>
            <p className="brand-subtitle">
              Predictive Infrastructure Risk & Dependency Cascade Engine
            </p>
          </div>
          <span className="badge-version">v{engineVersion}</span>
        </div>

        <div className="header-actions">
          <div className="health-pill" title={isBackendOnline ? 'Backend API reachable' : 'Backend API unreachable'}>
            <span className={`health-dot ${isBackendOnline ? 'online' : 'offline'}`} />
            <span>{isBackendOnline ? 'API Connected' : 'API Offline'}</span>
          </div>

          {hasReport && (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={onCopyMarkdown}
                title="Copy Markdown PR comment to clipboard"
              >
                {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                <span>{copied ? 'Copied!' : 'Copy PR Comment'}</span>
              </button>

              <button
                type="button"
                className="btn-secondary"
                onClick={onExportMarkdown}
                title="Download Markdown Report"
              >
                <Download size={14} />
                <span>Markdown</span>
              </button>

              <button
                type="button"
                className="btn-primary"
                onClick={onExportJson}
                title="Download JSON Report"
              >
                <Download size={14} />
                <span>JSON Report</span>
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
