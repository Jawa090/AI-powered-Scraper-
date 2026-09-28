/**
 * API Service connecting AI Powered frontend with the FastAPI backend
 * Uses VITE_API_BASE_URL (defaults to http://127.0.0.1:8000)
 */

import {
  Job,
  Lead,
  Dataset,
  Script,
  Requirement,
  BotChatResponse,
  BotConfirmResponse,
  SystemStatus,
} from '../types';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const API_BASE = `${BASE_URL}/api`;

class ApiService {
  public baseUrl: string = BASE_URL;

  /**
   * Probes application liveness and database readiness.
   */
  async getSystemStatus(): Promise<SystemStatus> {
    try {
      // 1. Check liveness (/health)
      const livenessRes = await fetch(`${BASE_URL}/health`, { method: 'GET' }).catch(() => null);
      const isAlive = livenessRes ? livenessRes.ok : false;
      let registeredScripts = 4;
      if (livenessRes && livenessRes.ok) {
        const data = await livenessRes.json().catch(() => ({}));
        registeredScripts = data.registeredScripts || 4;
      }

      // 2. Check readiness (/health/ready) for PostgreSQL
      const readyRes = await fetch(`${BASE_URL}/health/ready`, { method: 'GET' }).catch(() => null);
      const isDbReady = readyRes ? readyRes.ok : false;

      return {
        backend: isAlive,
        database: isDbReady,
        api: isAlive && isDbReady,
        timestamp: Date.now(),
        registeredScripts,
      };
    } catch (e: any) {
      return {
        backend: false,
        database: false,
        api: false,
        timestamp: Date.now(),
        registeredScripts: 0,
        error: e?.message || 'Connection failed',
      };
    }
  }

  /**
   * Simple liveness check
   */
  async getHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${BASE_URL}/health`, { method: 'GET' });
      return res.ok;
    } catch {
      return false;
    }
  }

  /**
   * Fetches all registered scraping engines with metadata.
   */
  async getScripts(): Promise<Script[]> {
    try {
      const res = await fetch(`${API_BASE}/scripts`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load scripts`);
      const data = await res.json();
      return data.scripts || [];
    } catch (e) {
      console.warn('API getScripts error:', e);
      return [];
    }
  }

  /**
   * Fetches detailed metadata for a single script.
   */
  async getScript(scriptId: string): Promise<Script | null> {
    try {
      const res = await fetch(`${API_BASE}/scripts/${scriptId}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data.script || null;
    } catch (e) {
      console.warn(`API getScript(${scriptId}) error:`, e);
      return null;
    }
  }

  /**
   * Triggers a scraping job in the background via Layer 4 execution.
   */
  async runScript(
    scriptId: string,
    parameters: Record<string, any> = {}
  ): Promise<{ success: boolean; jobId: string; message: string; scriptId: string }> {
    const res = await fetch(`${API_BASE}/scripts/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scriptId, parameters }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.error?.message || `HTTP ${res.status}: Failed to trigger script`);
    }
    return res.json();
  }

  /**
   * Fetches all active and completed scraper execution jobs.
   */
  async getJobs(): Promise<Job[]> {
    try {
      const res = await fetch(`${API_BASE}/jobs`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch jobs`);
      const data = await res.json();
      return data.jobs || [];
    } catch (e) {
      console.warn('API getJobs error:', e);
      return [];
    }
  }

  /**
   * Fetches real-time status and logs for a specific job.
   */
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

  /**
   * Fetches datasets created from scraper runs.
   */
  async getDatasets(): Promise<Dataset[]> {
    try {
      const res = await fetch(`${API_BASE}/datasets`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch datasets`);
      const data = await res.json();
      return data.datasets || [];
    } catch (e) {
      console.warn('API getDatasets error:', e);
      return [];
    }
  }

  /**
   * Fetches verified leads and opportunities extracted by scrapers.
   */
  async getLeads(datasetId?: string, query?: string): Promise<Lead[]> {
    try {
      const params = new URLSearchParams();
      if (datasetId) params.append('datasetId', datasetId);
      if (query) params.append('query', query);

      const url = `${API_BASE}/leads${params.toString() ? `?${params.toString()}` : ''}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch leads`);
      const data = await res.json();
      return data.leads || [];
    } catch (e) {
      console.warn('API getLeads error:', e);
      return [];
    }
  }

  /**
   * Sends user message to AI Agent Bot and receives structured response.
   * Supports Single Agent and Layer 12 Multi-Agent Collaboration.
   */
  async sendBotMessage(
    sessionId: string,
    message: string,
    currentRequirement?: Requirement,
    history?: any[]
  ): Promise<BotChatResponse | null> {
    try {
      const res = await fetch(`${API_BASE}/bot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          message,
          currentRequirement,
          history,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        console.warn(`Bot API returned HTTP ${res.status}:`, errData);
        return null;
      }
      return res.json();
    } catch (e) {
      console.warn('API sendBotMessage error:', e);
      return null;
    }
  }

  /**
   * Confirms requirement and triggers controlled pipeline execution.
   */
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
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        console.warn(`Confirm API returned HTTP ${res.status}:`, errData);
        return null;
      }
      return res.json();
    } catch (e) {
      console.warn('API confirmBotRequirement error:', e);
      return null;
    }
  }
}

export const apiService = new ApiService();
