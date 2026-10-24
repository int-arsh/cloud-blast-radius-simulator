import React, { useRef, useState } from 'react';
import { UploadCloud, FileCode, Layers, ShieldCheck, AlertCircle } from 'lucide-react';
import { SAMPLE_PLANS } from '../data/samplePlans';
import type { SamplePlanOption } from '../types';

interface PlanUploadProps {
  onAnalyze: (content: string | File, criticalResources?: string[]) => void;
  isLoading: boolean;
  selectedPresetId: string | null;
  onSelectPreset: (preset: SamplePlanOption) => void;
}

export const PlanUpload: React.FC<PlanUploadProps> = ({
  onAnalyze,
  isLoading,
  selectedPresetId,
  onSelectPreset,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [criticalInput, setCriticalInput] = useState('');
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseCriticalResources = (): string[] | undefined => {
    if (!criticalInput.trim()) return undefined;
    return criticalInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    setFileError(null);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      processFile(files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFileError(null);
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  const processFile = (file: File) => {
    if (!file.name.endsWith('.json')) {
      setFileError('Please upload a valid JSON Terraform plan file (*.json).');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setFileError('Plan file exceeds 10 MB limit.');
      return;
    }

    onAnalyze(file, parseCriticalResources());
  };

  const handlePresetClick = (preset: SamplePlanOption) => {
    setFileError(null);
    onSelectPreset(preset);
    onAnalyze(preset.jsonContent, parseCriticalResources());
  };

  return (
    <section className="glass-panel upload-section">
      <div className="upload-header">
        <div className="section-title">
          <FileCode size={20} color="#6366f1" />
          <span>Terraform Plan Simulation Input</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldCheck size={16} color="#94a3b8" />
          <input
            type="text"
            className="graph-search-input"
            style={{ width: '280px' }}
            placeholder="Critical resources (comma-separated)..."
            value={criticalInput}
            onChange={(e) => setCriticalInput(e.target.value)}
            title="Designate specific resource addresses as critical to enforce strict BLOCKED gates upon modification"
          />
        </div>
      </div>

      <div
        className={`upload-dropzone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".json,application/json"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        <div className="dropzone-icon">
          <UploadCloud size={24} />
        </div>

        <div>
          <p className="dropzone-title">
            {isLoading
              ? 'Analyzing Terraform Plan & Graph Dependencies...'
              : 'Drag & Drop Terraform Plan JSON or Click to Browse'}
          </p>
          <p className="dropzone-hint">
            Supports `terraform show -json tfplan.binary` format up to 10 MB. Zero real cloud mutations.
          </p>
        </div>
      </div>

      {fileError && (
        <div style={{ color: '#ef4444', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <AlertCircle size={14} />
          <span>{fileError}</span>
        </div>
      )}

      <div className="presets-container">
        <span className="presets-label">
          <Layers size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px' }} />
          Or Load Sample Infrastructure Scenario:
        </span>

        <div className="preset-chips-grid">
          {SAMPLE_PLANS.map((preset) => {
            const isSelected = selectedPresetId === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                className={`preset-chip ${isSelected ? 'active' : ''}`}
                onClick={() => handlePresetClick(preset)}
                disabled={isLoading}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                    <span className="chip-label">{preset.label}</span>
                    <span
                      className="chip-tag"
                      style={{
                        backgroundColor: `${preset.tagColor}22`,
                        color: preset.tagColor,
                        border: `1px solid ${preset.tagColor}55`,
                      }}
                    >
                      {preset.tag}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{preset.description}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
};
