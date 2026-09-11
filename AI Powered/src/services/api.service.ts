/**
 * API Service connecting AI Powered frontend with the FastAPI backend
 */

import { Job, Lead, Dataset, Script, Requirement } from '../types';

const API_BASE = 'http://localhost:8000/api';

export interface BotChatResponse {
  reply: string;
  suggestions: string[];
  updatedRequirement: Requirement;
  recommendedScript?: string;
}

export interface BotConfirmResponse {
  success: boolean;
  jobId: string;
  scriptId: string;
  datasetId: string;
  message: string;
}

class ApiService {
  async getHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
      return res.ok;
    } catch {
      return false;
    }
  }

  async getScripts(): Promise<Script[]> {
    try {
      const res = await fetch(`${API_BASE}/scripts`);
      if (!res.ok) throw new Error('Failed to load scripts');
      const data = await res.json();
      return data.scripts || [];
    } catch (e) {
      console.warn('API getScripts error, using local fallback:', e);
      return [];
    }
  }

  async runScript(scriptId: string, parameters: Record<string, any> = {}): Promise<{ jobId: string }> {
    const res = await fetch(`${API_BASE}/scripts/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scriptId, parameters }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to trigger script');
    }
    return res.json();
  }

  async getJobs(): Promise<Job[]> {
    try {
      const res = await fetch(`${API_BASE}/jobs`);
      if (!res.ok) throw new Error('Failed to fetch jobs');
      const data = await res.json();
      return data.jobs || [];
    } catch (e) {
      console.warn('API getJobs error:', e);
      return [];
    }
  }

  async getJob(jobId: string): Promise<Job | null> {
    try {
      const res = await fetch(`${API_BASE}/jobs/${jobId}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data.job || null;
    } catch (e) {
      console.warn(`API getJob(${jobId}) error:`, e);
      return null;
    }
  }

  async getDatasets(): Promise<Dataset[]> {
    try {
      const res = await fetch(`${API_BASE}/datasets`);
      if (!res.ok) throw new Error('Failed to fetch datasets');
      const data = await res.json();
      return data.datasets || [];
    } catch (e) {
      console.warn('API getDatasets error:', e);
      return [];
    }
  }

  async getLeads(datasetId?: string, query?: string): Promise<Lead[]> {
    try {
      const params = new URLSearchParams();
      if (datasetId) params.append('datasetId', datasetId);
      if (query) params.append('query', query);

      const res = await fetch(`${API_BASE}/leads?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch leads');
      const data = await res.json();
      return data.leads || [];
    } catch (e) {
      console.warn('API getLeads error:', e);
      return [];
    }
  }

  async sendBotMessage(
    sessionId: string,
    message: string,
    currentRequirement?: Requirement
  ): Promise<BotChatResponse | null> {
    try {
      const res = await fetch(`${API_BASE}/bot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          message,
          currentRequirement,
        }),
      });
      if (!res.ok) return null;
      return res.json();
    } catch (e) {
      console.warn('API sendBotMessage error:', e);
      return null;
    }
  }

  async confirmBotRequirement(
    sessionId: string,
    requirement: Requirement,
    preferredScriptId?: string
  ): Promise<BotConfirmResponse | null> {
    try {
      const res = await fetch(`${API_BASE}/bot/confirm-and-generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          requirement,
          preferredScriptId,
        }),
      });
      if (!res.ok) return null;
      return res.json();
    } catch (e) {
      console.warn('API confirmBotRequirement error:', e);
      return null;
    }
  }
}

export const apiService = new ApiService();
