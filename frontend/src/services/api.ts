import type { FullAnalysisReport } from '../types';

const API_BASE = '/api/v1';

export async function analyzePlan(
  payload: string | File,
  criticalResources?: string[]
): Promise<FullAnalysisReport> {
  const queryParams = new URLSearchParams();
  if (criticalResources && criticalResources.length > 0) {
    criticalResources.forEach((res) => queryParams.append('critical_resources', res));
  }

  const url = `${API_BASE}/analyze${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;

  let headers: HeadersInit = {};
  let body: BodyInit;

  if (payload instanceof File) {
    const formData = new FormData();
    formData.append('file', payload);
    body = formData;
  } else {
    headers = { 'Content-Type': 'application/json' };
    body = payload;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body,
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errData.detail || `Analysis request failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function exportReport(
  payload: string | File,
  format: 'markdown' | 'json'
): Promise<string> {
  const url = `${API_BASE}/analyze/export?format=${format}`;

  let headers: HeadersInit = {};
  let body: BodyInit;

  if (payload instanceof File) {
    const formData = new FormData();
    formData.append('file', payload);
    body = formData;
  } else {
    headers = { 'Content-Type': 'application/json' };
    body = payload;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body,
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errData.detail || `Export request failed with HTTP ${response.status}`);
  }

  return response.text();
}

export async function checkBackendHealth(): Promise<{ status: string; version: string } | null> {
  try {
    const response = await fetch('/health', { signal: AbortSignal.timeout(3000) });
    if (response.ok) {
      return response.json();
    }
    return null;
  } catch {
    return null;
  }
}
