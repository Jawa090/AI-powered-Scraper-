/**
 * API Service connecting AI Powered frontend with the FastAPI backend
 * Uses VITE_API_BASE_URL (defaults to http://127.0.0.1:8000)
 * P13: Authenticated fetch, JWT session storage, automatic 401 logout,
 * chat clientMessageId generation, 503 retry support, and admin endpoints.
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
  User,
  AdminUser,
  AdminRequestItem,
  AdminRequestDetail,
  RagStatus,
  RagDocument,
} from '../types';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const API_BASE = `${BASE_URL}/api`;
const TOKEN_STORAGE_KEY = 'dataops_jwt_token';

export interface LoginResponse {
  accessToken: string;
  tokenType: string;
  expiresIn: number;
  user: User;
}

export interface BotChatResult {
  data?: BotChatResponse;
  is503?: boolean;
  error?: string;
}

class ApiService {
  public baseUrl: string = BASE_URL;
  private token: string | null = null;
  private onUnauthorizedCallback: (() => void) | null = null;

  constructor() {
    this.token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
  }

  public setToken(token: string | null) {
    this.token = token;
    if (token) {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  }

  public getToken(): string | null {
    return this.token || sessionStorage.getItem(TOKEN_STORAGE_KEY);
  }

  public setOnUnauthorized(callback: () => void) {
    this.onUnauthorizedCallback = callback;
  }

  private handleUnauthorized() {
    this.setToken(null);
    if (this.onUnauthorizedCallback) {
      this.onUnauthorizedCallback();
    }
  }

  /**
   * Helper for authenticated HTTP requests.
   * Injects Authorization header and handles 401 automatic logout.
   */
  public async fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(options.headers || {});
    const token = this.getToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    try {
      const response = await fetch(url, { ...options, headers });
      if (response.status === 401) {
        this.handleUnauthorized();
      }
      return response;
    } catch (err) {
      throw err;
    }
  }

  // ---------------------------------------------------------------------------
  // Auth Endpoints
  // ---------------------------------------------------------------------------

  async login(username: string, password: string): Promise<LoginResponse> {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.error?.message || `Login failed (${res.status})`);
    }

    const data: LoginResponse = await res.json();
    this.setToken(data.accessToken);
    return data;
  }

  async getMe(): Promise<User | null> {
    if (!this.getToken()) return null;
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/auth/me`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  logout() {
    this.setToken(null);
  }

  // ---------------------------------------------------------------------------
  // Health & System Status
  // ---------------------------------------------------------------------------

  async getSystemStatus(): Promise<SystemStatus> {
    try {
      const livenessRes = await fetch(`${BASE_URL}/health`, { method: 'GET' }).catch(() => null);
      const isAlive = livenessRes ? livenessRes.ok : false;
      let registeredScripts = 4;
      if (livenessRes && livenessRes.ok) {
        const data = await livenessRes.json().catch(() => ({}));
        registeredScripts = data.registeredScripts || 4;
      }

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

  async getHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${BASE_URL}/health`, { method: 'GET' });
      return res.ok;
    } catch {
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Scripts & Jobs
  // ---------------------------------------------------------------------------

  async getScripts(): Promise<Script[]> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/scripts`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load scripts`);
      const data = await res.json();
      return data.scripts || [];
    } catch (e) {
      console.warn('API getScripts error:', e);
      return [];
    }
  }

  async getScript(scriptId: string): Promise<Script | null> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/scripts/${scriptId}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data.script || null;
    } catch (e) {
      console.warn(`API getScript(${scriptId}) error:`, e);
      return null;
    }
  }

  async runScript(
    scriptId: string,
    parameters: Record<string, any> = {}
  ): Promise<{ success: boolean; jobId: string; message: string; scriptId: string }> {
    const res = await this.fetchWithAuth(`${API_BASE}/scripts/run`, {
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

  async getJobs(): Promise<Job[]> {
    const rows: Job[] = [];
    let page = 1;
    while (true) {
      const res = await this.fetchWithAuth(`${API_BASE}/jobs?page=${page}&pageSize=100`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch jobs`);
      const data = await res.json();
      rows.push(...(data.jobs || []));
      if (!data.jobs?.length || rows.length >= (data.total ?? rows.length)) return rows;
      page += 1;
    }
  }

  async getJob(jobId: string): Promise<Job | null> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/jobs/${jobId}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data.job || null;
    } catch (e) {
      console.warn(`API getJob(${jobId}) error:`, e);
      return null;
    }
  }

  async cancelJob(jobId: string): Promise<boolean> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/jobs/${jobId}/cancel`, {
        method: 'POST',
      });
      return res.ok;
    } catch (e) {
      console.warn(`API cancelJob(${jobId}) error:`, e);
      return false;
    }
  }

  async resumeJob(jobId: string): Promise<void> {
    const response = await this.fetchWithAuth(`${API_BASE}/jobs/${jobId}/resume`, { method: 'POST' });
    if (!response.ok) throw new Error('Could not resume this job.');
  }

  async downloadAuthenticated(url: string, filename: string): Promise<void> {
    const response = await this.fetchWithAuth(url);
    if (!response.ok) throw new Error(`Download failed (${response.status})`);
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement('a'); link.href = objectUrl; link.download = filename;
    link.click(); URL.revokeObjectURL(objectUrl);
  }

  // ---------------------------------------------------------------------------
  // Leads & Datasets
  // ---------------------------------------------------------------------------

  async getDatasets(): Promise<Dataset[]> {
    const rows: Dataset[] = [];
    let page = 1;
    while (true) {
      const res = await this.fetchWithAuth(`${API_BASE}/datasets?page=${page}&pageSize=100`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch datasets`);
      const data = await res.json();
      rows.push(...(data.datasets || []));
      if (!data.datasets?.length || rows.length >= (data.total ?? rows.length)) return rows;
      page += 1;
    }
  }

  async getLeads(datasetId?: string, query?: string, page?: number, pageSize: number = 100): Promise<Lead[]> {
    try {
      const params = new URLSearchParams();
      if (datasetId) params.append('datasetId', datasetId);
      if (query) params.append('query', query);
      params.append('page', String(page || 1));
      params.append('page_size', String(pageSize));

      const url = `${API_BASE}/leads?${params.toString()}`;
      const res = await this.fetchWithAuth(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch leads`);
      const data = await res.json();
      const rows = data.leads || [];
      if (page === undefined) {
        for (let next = 2; rows.length < data.total; next++) {
          const batch = await this.getLeads(datasetId, query, next, pageSize);
          if (!batch.length) break;
          rows.push(...batch);
        }
      }
      return rows;
    } catch (e) {
      console.warn('API getLeads error:', e);
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // AI Agent Bot Endpoints
  // ---------------------------------------------------------------------------

  async createNewChat(previousSessionId?: string): Promise<{ sessionId: string; clearedSessionIds?: string[] }> {
    const res = await this.fetchWithAuth(`${API_BASE}/bot/chat/new`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ previousSessionId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to create chat session`);
    return res.json();
  }

  async getBotState(sessionId: string): Promise<any> {
    const res = await this.fetchWithAuth(`${API_BASE}/bot/state?sessionId=${sessionId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch bot state`);
    return res.json();
  }

  async updateJob(sessionId: string, jobId: string): Promise<BotChatResult> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/bot/job-update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, jobId }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        return { error: errData.detail || `HTTP ${res.status}` };
      }
      const data = await res.json();
      return { data };
    } catch (e: any) {
      return { error: e?.message || 'Network error updating job' };
    }
  }

  /**
   * Sends user message to AI Agent Bot.
   * Generates or passes clientMessageId.
   * Explicitly avoids sending conversation history.
   * Handles 503 LLM_UNAVAILABLE responses.
   */
  async sendBotMessage(
    sessionId: string,
    message: string,
    clientMessageId: string,
    currentRequirement?: Requirement,
    newOnly = false,
    expectedProposalId?: string,
    signal?: AbortSignal
  ): Promise<BotChatResult> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/bot/chat`, {
        signal,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          message,
          clientMessageId,
          currentRequirement,
          newOnly,
          expectedProposalId,
        }),
      });

      if (res.status === 503) {
        const errData = await res.json().catch(() => ({}));
        return {
          is503: true,
          error: 'Server is Down',
        };
      }

      if (!res.ok) {
        return {
          is503: true,
          error: 'Server is Down',
        };
      }

      const data = await res.json();
      return { data };
    } catch (e: any) {
      console.warn('API sendBotMessage error:', e);
      return {
        is503: true,
        error: 'Server is Down',
      };
    }
  }

  /**
   * Confirms or rejects a proposal via /api/bot/confirm.
   */
  async confirmBot(
    sessionId: string,
    decision: 'approve' | 'reject',
    clientMessageId?: string
  ): Promise<BotChatResult> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/bot/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          decision,
          clientMessageId,
        }),
      });

      if (res.status === 503) {
        return {
          is503: true,
          error: 'Server is Down',
        };
      }

      if (!res.ok) {
        return { is503: true, error: 'Server is Down' };
      }

      const data = await res.json();
      return { data };
    } catch (e: any) {
      return { is503: true, error: 'Server is Down' };
    }
  }

  /**
   * Legacy confirm requirement and trigger pipeline execution.
   */
  async confirmBotRequirement(
    sessionId: string,
    requirement: Requirement,
    preferredScriptId?: string
  ): Promise<BotConfirmResponse | null> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/bot/confirm-and-generate`, {
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

  /**
   * Polls messages for active job monitoring.
   */
  async getSessionMessages(sessionId: string): Promise<Array<{ id: string; sender: string; text: string; createdAt?: string }>> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/bot/sessions/${sessionId}/messages`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.messages || [];
    } catch {
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // Admin Endpoints
  // ---------------------------------------------------------------------------

  async getAdminUsers(): Promise<AdminUser[]> {
    const res = await this.fetchWithAuth(`${API_BASE}/admin/users`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch users`);
    return res.json();
  }

  async createAdminUser(payload: { name?: string; email?: string; username: string; password: string; role?: string }): Promise<{ id: string; message: string }> {
    const res = await this.fetchWithAuth(`${API_BASE}/admin/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to create user (${res.status})`);
    }
    return res.json();
  }

  async updateAdminUser(userId: string, payload: { email?: string; name?: string; password?: string; status?: string }): Promise<{ message: string }> {
    const res = await this.fetchWithAuth(`${API_BASE}/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update user (${res.status})`);
    }
    return res.json();
  }

  async disableAdminUser(userId: string): Promise<{ message: string }> {
    const res = await this.fetchWithAuth(`${API_BASE}/admin/users/${userId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to disable user (${res.status})`);
    }
    return res.json();
  }

  async getAdminRequests(params: {
    userId?: string;
    decision?: string;
    source?: string;
    from?: string;
    to?: string;
    page?: number;
    pageSize?: number;
  } = {}): Promise<{ items: AdminRequestItem[]; total: number; page: number; pageSize: number }> {
    const q = new URLSearchParams();
    if (params.userId) q.append('user_id', params.userId);
    if (params.decision) q.append('decision', params.decision);
    if (params.source) q.append('source', params.source);
    if (params.from) q.append('from', params.from);
    if (params.to) q.append('to', params.to);
    if (params.page) q.append('page', String(params.page));
    if (params.pageSize) q.append('page_size', String(params.pageSize));

    const res = await this.fetchWithAuth(`${API_BASE}/admin/requests?${q.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch admin requests`);
    return res.json();
  }

  async getAdminRequestDetail(requestId: string): Promise<AdminRequestDetail> {
    const res = await this.fetchWithAuth(`${API_BASE}/admin/requests/${requestId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch request detail`);
    return res.json();
  }

  async getAdminStats(): Promise<any> {
    const res = await this.fetchWithAuth(`${API_BASE}/admin/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch admin stats`);
    return res.json();
  }

  getAdminRequestsExportUrl(params: { userId?: string; decision?: string; from?: string; to?: string } = {}): string {
    const q = new URLSearchParams();
    if (params.userId) q.append('user_id', params.userId);
    if (params.decision) q.append('decision', params.decision);
    if (params.from) q.append('from', params.from);
    if (params.to) q.append('to', params.to);
    return `${API_BASE}/admin/requests/export.csv?${q.toString()}`;
  }

  // ---------------------------------------------------------------------------
  // Knowledge Base (RAG) Endpoints
  // ---------------------------------------------------------------------------

  async getRagStatus(): Promise<RagStatus> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/rag/v1/status`);
      if (!res.ok) {
        return {
          state: 'not_configured',
          available: false,
          message: `RAG service returned status ${res.status}`,
        };
      }
      return await res.json();
    } catch {
      return {
        state: 'error',
        available: false,
        message: 'Could not connect to Knowledge Base service',
      };
    }
  }

  async getRagDocuments(): Promise<RagDocument[]> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/rag/v1/documents`);
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : data.documents || [];
    } catch {
      return [];
    }
  }

  async uploadRagDocument(content: string, title?: string): Promise<boolean> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/rag/v1/documents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, title: title || 'Uploaded Document' }),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async deleteRagDocument(docId: string): Promise<boolean> {
    try {
      const res = await this.fetchWithAuth(`${API_BASE}/rag/v1/documents/${docId}`, {
        method: 'DELETE',
      });
      return res.ok;
    } catch {
      return false;
    }
  }
}

export const apiService = new ApiService();
