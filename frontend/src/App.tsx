import React, { useEffect, useState } from 'react';
import { Header } from './components/Header';
import { PlanUpload } from './components/PlanUpload';
import { SummaryCards } from './components/SummaryCards';
import { DependencyGraph } from './components/DependencyGraph';
import { ResourceInspector } from './components/ResourceInspector';
import { FindingsTable } from './components/FindingsTable';
import { WarningsBanner } from './components/WarningsBanner';
import { SAMPLE_PLANS } from './data/samplePlans';
import type { FullAnalysisReport, SamplePlanOption } from './types';
import { analyzePlan, exportReport, checkBackendHealth } from './services/api';
import { AlertCircle, CheckCircle } from 'lucide-react';

export const App: React.FC = () => {
  const [report, setReport] = useState<FullAnalysisReport | null>(null);
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(SAMPLE_PLANS[0].id);
  const [currentPayload, setCurrentPayload] = useState<string | File>(SAMPLE_PLANS[0].jsonContent);
  const [selectedNodeAddress, setSelectedNodeAddress] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isBackendOnline, setIsBackendOnline] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleAnalyze = async (
    payload: string | File,
    criticalResources?: string[]
  ) => {
    setIsLoading(true);
    setErrorMessage(null);
    setCurrentPayload(payload);

    try {
      const result = await analyzePlan(payload, criticalResources);
      setReport(result);
      // Auto-select first changed or critical resource if available
      if (result.resource_counts.changed > 0 && result.impact_summary.resource_blast_radii.length > 0) {
        setSelectedNodeAddress(result.impact_summary.resource_blast_radii[0].resource_address);
      } else if (result.nodes.length > 0) {
        setSelectedNodeAddress(result.nodes[0].address);
      }
    } catch (err: any) {
      console.error('Simulation error:', err);
      setErrorMessage(err.message || 'Failed to analyze Terraform plan.');
    } finally {
      setIsLoading(false);
    }
  };

  // Check health and run initial simulation with the first preset
  useEffect(() => {
    let isMounted = true;

    async function init() {
      const health = await checkBackendHealth();
      if (isMounted) {
        setIsBackendOnline(!!health);
      }
      // Run initial analysis with first preset
      handleAnalyze(SAMPLE_PLANS[0].jsonContent);
    }

    init();

    // Periodic health check
    const interval = setInterval(async () => {
      const h = await checkBackendHealth();
      if (isMounted) {
        setIsBackendOnline(!!h);
      }
    }, 10000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleSelectPreset = (preset: SamplePlanOption) => {
    setSelectedPresetId(preset.id);
  };

  const downloadFile = (filename: string, content: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleExportMarkdown = async () => {
    if (!currentPayload) return;
    try {
      const md = await exportReport(currentPayload, 'markdown');
      downloadFile(`blast-radius-report-${Date.now()}.md`, md, 'text/markdown');
      showToast('Markdown report downloaded.');
    } catch (err: any) {
      setErrorMessage(`Export failed: ${err.message}`);
    }
  };

  const handleExportJson = async () => {
    if (!currentPayload) return;
    try {
      const json = await exportReport(currentPayload, 'json');
      downloadFile(`blast-radius-report-${Date.now()}.json`, json, 'application/json');
      showToast('JSON report downloaded.');
    } catch (err: any) {
      setErrorMessage(`Export failed: ${err.message}`);
    }
  };

  const handleCopyMarkdown = async () => {
    if (!currentPayload) return;
    try {
      const md = await exportReport(currentPayload, 'markdown');
      await navigator.clipboard.writeText(md);
      setCopied(true);
      showToast('PR comment markdown copied to clipboard!');
      setTimeout(() => setCopied(false), 2500);
    } catch (err: any) {
      setErrorMessage(`Copy failed: ${err.message}`);
    }
  };

  return (
    <div className="app-container">
      <Header
        engineVersion={report?.engine_version || '0.1.0'}
        isBackendOnline={isBackendOnline}
        onExportMarkdown={handleExportMarkdown}
        onExportJson={handleExportJson}
        onCopyMarkdown={handleCopyMarkdown}
        copied={copied}
        hasReport={!!report}
      />

      <main className="main-content">
        {/* Error Notification */}
        {errorMessage && (
          <div
            style={{
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 18px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              color: '#f87171',
              fontSize: '0.85rem',
            }}
          >
            <AlertCircle size={18} />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Upload & Scenario Presets */}
        <PlanUpload
          onAnalyze={handleAnalyze}
          isLoading={isLoading}
          selectedPresetId={selectedPresetId}
          onSelectPreset={handleSelectPreset}
        />

        {/* Executive Summary Cards */}
        {report && <SummaryCards report={report} />}

        {/* Warnings Banner */}
        {report && report.warnings && report.warnings.length > 0 && (
          <WarningsBanner warnings={report.warnings} />
        )}

        {/* Main Workspace Grid: Interactive DAG Visualizer + Resource Inspector */}
        {report && (
          <div className="dashboard-grid">
            <DependencyGraph
              report={report}
              selectedNodeAddress={selectedNodeAddress}
              onSelectNode={(addr) => setSelectedNodeAddress(addr)}
            />

            <ResourceInspector
              report={report}
              selectedAddress={selectedNodeAddress}
              onClose={() => setSelectedNodeAddress(null)}
              onSelectAddress={(addr) => setSelectedNodeAddress(addr)}
            />
          </div>
        )}

        {/* Findings and Rule Violations Table */}
        {report && (
          <FindingsTable
            findings={report.findings}
            onSelectResource={(addr) => {
              setSelectedNodeAddress(addr);
              window.scrollTo({ top: 380, behavior: 'smooth' });
            }}
          />
        )}
      </main>

      {/* Toast Notification */}
      {toastMessage && (
        <div className="toast-notice">
          <CheckCircle size={16} color="#10b981" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
};

export default App;
