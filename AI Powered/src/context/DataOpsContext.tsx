import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import {
  User,
  UserRole,
  Lead,
  LeadStatus,
  Dataset,
  Activity,
  Department,
  AgentSession,
  AgentMessage,
  Requirement,
  Job,
} from '../types';
import { agentService } from '../services/agent.service';
import { apiService } from '../services/api.service';
import { useAuth } from './AuthContext';

export interface ToastMessage {
  id: string;
  type: 'success' | 'info' | 'warning' | 'error';
  title: string;
  message: string;
}

interface DataOpsContextType {
  // User & Auth
  currentUser: User;
  switchUser: (userId: string) => void;
  switchRole: (role: UserRole) => void;
  allUsers: User[];

  // Reactive Domain Data
  leads: Lead[];
  datasets: Dataset[];
  activities: Activity[];
  departments: Department[];
  jobs: Job[];

  // Global KPIs
  kpis: {
    totalLeads: number;
    generatedToday: number;
    callsCompleted: number;
    emailsSent: number;
    interestedLeads: number;
    pendingActions: number;
  };

  // Lead Actions
  logCall: (leadId: string, outcome: LeadStatus, notes: string, nextFollowUp?: string) => Promise<void>;
  sendEmail: (leadId: string, subject: string, body: string) => Promise<void>;
  sendBulkEmail: (leadIds: string[], subject: string, body: string) => Promise<void>;
  updateLeadStatus: (leadId: string, status: LeadStatus) => Promise<void>;

  // AI Agent & Data Generation
  sessions: AgentSession[];
  activeSessionId: string;
  newOnly: boolean;
  setNewOnly: (value: boolean) => void;
  setActiveSessionId: (id: string) => void;
  messagesBySession: Record<string, AgentMessage[]>;
  sendMessage: (sessionId: string, text: string) => Promise<string | undefined>;
  confirmBotDecision: (sessionId: string, decision: 'approve' | 'reject', proposalId?: string) => Promise<void>;
  retryBotMessage: (sessionId: string, clientMessageId: string, text: string) => Promise<void>;
  clearChat: () => void;
  confirmRequirementAndGenerate: (sessionId: string) => Promise<string>; // returns jobId or reqId
  getLiveJob: (jobId: string) => Job | undefined;

  // Search & Filters
  globalSearch: string;
  setGlobalSearch: (q: string) => void;

  // Notifications / Toasts
  toasts: ToastMessage[];
  showToast: (title: string, message: string, type?: ToastMessage['type']) => void;
  removeToast: (id: string) => void;
  notifications: { id: string; title: string; desc: string; time: string; read: boolean }[];
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
}

const DataOpsContext = createContext<DataOpsContextType | undefined>(undefined);

export const DataOpsProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user: authUser } = useAuth();
  const [currentUser, setCurrentUser] = useState<User>(() => {
    if (authUser) {
      return {
        id: authUser.id,
        username: authUser.username,
        name: authUser.name || authUser.username || 'User',
        email: authUser.email || '',
        role: authUser.role,
        roleTitle: authUser.role === 'admin' ? 'Head of Enterprise Intelligence (Admin)' : 'Outbound Specialist',
        departmentName: authUser.role === 'admin' ? 'State Contracts & Regulatory' : 'Procurement & Municipal Bids',
      };
    }
    return { id: '', username: '', name: 'Guest', role: 'user', roleTitle: '', email: '' };
  });

  useEffect(() => {
    if (authUser) {
      setCurrentUser(prev => ({
        ...prev,
        id: authUser.id,
        username: authUser.username,
        name: authUser.name || authUser.username || 'User',
        email: authUser.email || '',
        role: authUser.role,
        roleTitle: authUser.role === 'admin' ? 'Head of Enterprise Intelligence (Admin)' : 'Outbound Specialist',
        departmentName: authUser.role === 'admin' ? 'State Contracts & Regulatory' : (prev.departmentName || 'Procurement & Municipal Bids'),
      }));
    }
  }, [authUser]);

  const [leads, setLeads] = useState<Lead[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [globalSearch, setGlobalSearch] = useState('');
  const [newOnly, setNewOnly] = useState(false);
  const monitors = useRef(new Map<string, ReturnType<typeof setInterval>>());
  const clearedSessions = useRef(new Set<string>());
  const chatRequests = useRef(new Map<string, AbortController>());

  // Initial KPIs
  const [kpiDeltas, setKpiDeltas] = useState({
    calls: 0,
    emails: 0,
    interested: 0,
    generated: 0,
  });

  // Sessions
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('sess-live-init');
  const [messagesBySession, setMessagesBySession] = useState<Record<string, AgentMessage[]>>({});

  // Notifications
  const [notifications, setNotifications] = useState<
    { id: string; title: string; desc: string; time: string; read: boolean }[]
  >([]);

  useEffect(() => {
    let cancelled = false;
    for (const timer of monitors.current.values()) clearInterval(timer);
    monitors.current.clear();
    setMessagesBySession({}); setSessions([]); setLeads([]); setJobs([]); setDatasets([]);
    if (!authUser) return;
    const restore = async () => {
      try {
        const res = await apiService.fetchWithAuth(`${apiService.baseUrl}/api/bot/sessions`);
        if (!res.ok) throw new Error('Cannot restore conversations');
        const data = await res.json();
        let row = data.sessions.find((session: any) => session.status === 'active');
        if (!row) {
          const created = await apiService.createNewChat();
          row = { id: created.sessionId, status: 'active', title: 'Active request' };
        }
        const requirement: Requirement = {
          id: `req-${row.id}`, sessionId: row.id, industry: '', location: '', companySize: '',
          decisionMakers: [], quantity: 0, completionPercentage: 0, status: 'collecting',
          requiredFields: { companyName: true, contactName: false, jobTitle: false, email: false, phone: false, website: false },
        };
        const msgs = await apiService.getSessionMessages(row.id);
        const state = await apiService.getBotState(row.id);
        if (cancelled) return;
        setSessions([{ ...row, agentId: row.agentId || 'agent-master', departmentId: row.departmentId || 'dept-default',
          createdAt: row.createdAt || '', updatedAt: row.updatedAt || '', requirement }]);
        setActiveSessionId(row.id);
        const restored = msgs.map((message: any) => ({ ...message, ...message.metadata, pendingAction: null, proposedActions: [],
          timestamp: new Date(message.createdAt).toLocaleTimeString() }));
        if (state.pendingAction && restored.length) {
          restored[restored.length - 1] = { ...restored[restored.length - 1],
            pendingAction: state.pendingAction, proposedActions: state.proposedActions };
        }
        setMessagesBySession({ [row.id]: restored });
        if (state.activeJobId) monitorJob(row.id, state.activeJobId);
        for (const jobId of state.pendingEventJobIds || []) monitorJob(row.id, jobId);
      } catch (err) {
        if (!cancelled) showToast('Could not restore chat', err instanceof Error ? err.message : 'Network error', 'error');
      }
    };
    void restore();
    return () => { cancelled = true; for (const timer of monitors.current.values()) clearInterval(timer); monitors.current.clear(); };
  }, [authUser?.id]);

  useEffect(() => {
    import('../services/chatStorage').then(({ saveChatData }) => {
      const msgs = messagesBySession[activeSessionId];
      if (msgs && msgs.length > 0) {
        // Find last pendingAction
        let pendingAction = null;
        let activeJobId = null;
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].pendingAction) pendingAction = msgs[i].pendingAction;
          if ((msgs[i] as any).jobId) activeJobId = (msgs[i] as any).jobId;
          if (pendingAction || activeJobId) break;
        }

        saveChatData(currentUser.id, {
          sessionId: activeSessionId,
          messages: msgs as any,
          pendingAction,
          activeJobId,
          updatedAt: new Date().toISOString()
        });
      }
    });
  }, [messagesBySession, activeSessionId, currentUser.id]);

  useEffect(() => {
    // Sync live datasets, jobs, and leads from FastAPI backend
    if (!authUser) return;

    apiService.getHealth().then(healthy => {
      if (healthy) {
        apiService.getDatasets().then(ds => { if (ds) setDatasets(ds); }).catch(() => showToast("Cannot load datasets", "Please retry when the API is available.", "error"));
        apiService.getJobs().then(jb => { if (jb) setJobs(jb); }).catch(() => showToast("Cannot load jobs", "Please retry when the API is available.", "error"));
        apiService.getLeads().then(ld => {
          if (ld) setLeads(ld);
          if (ld && ld.length > 0) {
            setKpiDeltas(prev => ({
              ...prev,
              generated: ld.length,
            }));
            showToast(
              'FastAPI Connected',
              `Loaded ${ld.length} live records from PostgreSQL.`,
              'success'
            );
          }
        });
      }
    });
  }, [authUser]);

  const showToast = (title: string, message: string, type: ToastMessage['type'] = 'success') => {
    const id = `toast-${Date.now()}-${Math.random()}`;
    setToasts(prev => [...prev, { id, title, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4500);
  };

  const monitorJob = (sessionId: string, jobId: string) => {
    if (monitors.current.has(jobId)) return;
    let busy = false;
    const poll = async () => {
      if (busy) return;
      busy = true;
      try {
        const job = await apiService.getJob(jobId);
        if (!job) return;
        setJobs(prev => [job, ...prev.filter(row => row.id !== jobId)]);
        setSessions(prev => prev.map(row => row.id === sessionId ? { ...row,
          requirement: { ...row.requirement, jobId, completionPercentage: job.progress || 0, status: job.status } } : row));
        if (!['Completed', 'Partial', 'Failed', 'Cancelled'].includes(job.status)) return;
        const response = await apiService.updateJob(sessionId, jobId);
        if (clearedSessions.current.has(sessionId) || !response.data || (response.data as any).pending) return;
        if (!(response.data as any).alreadyDelivered && response.data.reply) {
          const data = response.data;
          const message: AgentMessage = { id: `${data.queryId}:agent`, sessionId, sender: 'agent',
            text: data.reply, queryId: data.queryId, records: data.records, total: data.total,
            showAllDetails: data.showAllDetails,
            requestFulfilled: data.requestFulfilled, deliveryKind: data.deliveryKind,
            matchingRecordsDelivered: data.matchingRecordsDelivered, requestedRecords: data.requestedRecords,
            recoveredRecords: data.recoveredRecords, understoodRequest: data.understoodRequest,
            timedOut: data.timedOut, timeoutOptions: data.timeoutOptions, collectionCancelled: data.collectionCancelled,
            timestamp: new Date().toLocaleTimeString() };
          setMessagesBySession(prev => ({ ...prev, [sessionId]: [...(prev[sessionId] || []).filter(row => row.id !== message.id), message] }));
          setLeads(prev => [...(data.records || []), ...prev.filter(row => !(data.records || []).some(record => record.id === row.id))]);
        }
        if ((response.data as any).morePending) return;
        clearInterval(monitors.current.get(jobId)); monitors.current.delete(jobId);
        void apiService.getDatasets().then(setDatasets).catch(() => {});
      } catch (error) { console.warn("Job polling will retry", error); } finally { busy = false; }
    };
    monitors.current.set(jobId, setInterval(() => { void poll(); }, 3000));
    void poll();
  };

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const markNotificationRead = (id: string) => {
    setNotifications(prev => prev.map(n => (n.id === id ? { ...n, read: true } : n)));
  };

  const markAllNotificationsRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const switchUser = () => {};
  const switchRole = () => {};

  // -------------------------------------------------------------
  // Lead Actions: Call, Email, Bulk Email, Status
  // -------------------------------------------------------------
  const logCall = async (leadId: string, outcome: LeadStatus, notes: string, nextFollowUp?: string) => {
    const lead = leads.find(l => l.id === leadId);
    if (!lead) return;

    // Update lead
    setLeads(prev =>
      prev.map(l =>
        l.id === leadId
          ? {
              ...l,
              status: outcome,
              notes: notes || l.notes,
              nextFollowUp: nextFollowUp || l.nextFollowUp,
              lastActivity: `Call completed (${outcome})`,
            }
          : l
      )
    );

    // Update KPIs
    const isInterested = outcome === 'Interested' || outcome === 'Qualified';
    setKpiDeltas(prev => ({
      ...prev,
      calls: prev.calls + 1,
      interested: isInterested ? prev.interested + 1 : prev.interested,
    }));

    // Add Activity
    const newAct: Activity = {
      id: `act-${Date.now()}`,
      type: 'call',
      title: `Call logged with ${lead.name || lead.company || 'Lead'}`,
      description: `${currentUser.name} completed call with ${lead.name || 'contact'} (${lead.company || 'organization'}). Outcome: ${outcome}.${notes ? ` Note: "${notes}"` : ''}`,
      user: currentUser.name,
      department: currentUser.departmentName || 'General',
      timestamp: 'Just now',
      leadId: lead.id,
      leadName: lead.name || undefined,
      badgeColor: outcome === 'Interested' ? '#10B981' : outcome === 'Follow Up' ? '#F59E0B' : '#3B82F6',
    };
    setActivities(prev => [newAct, ...prev]);

    // Update Department Stats
    setDepartments(prev =>
      prev.map(d => {
        if (d.id === lead.departmentId) {
          const calledCount = d.calledCount + 1;
          const interestedCount = isInterested ? d.interestedCount + 1 : d.interestedCount;
          const pendingCount = Math.max(0, d.pendingCount - 1);
          const completionRate = Math.min(100, Math.round(((calledCount + d.emailedCount) / d.assignedCount) * 100));
          return { ...d, calledCount, interestedCount, pendingCount, completionRate };
        }
        return d;
      })
    );

    showToast('Call Logged', `Call with ${lead.name} saved as "${outcome}".`, 'success');
  };

  const sendEmail = async (leadId: string, subject: string, body: string) => {
    const lead = leads.find(l => l.id === leadId);
    if (!lead) return;

    setLeads(prev =>
      prev.map(l =>
        l.id === leadId
          ? { ...l, status: 'Emailed', lastActivity: 'Email sent just now' }
          : l
      )
    );

    setKpiDeltas(prev => ({ ...prev, emails: prev.emails + 1 }));

    const newAct: Activity = {
      id: `act-${Date.now()}`,
      type: 'email',
      title: `Email sent to ${lead.name || lead.company || 'Lead'}`,
      description: `${currentUser.name} sent "${subject}" to ${lead.email || 'recipient'} (${lead.company || 'organization'}).`,
      user: currentUser.name,
      department: currentUser.departmentName || 'General',
      timestamp: 'Just now',
      leadId: lead.id,
      leadName: lead.name || undefined,
      badgeColor: '#8B5CF6',
    };
    setActivities(prev => [newAct, ...prev]);

    setDepartments(prev =>
      prev.map(d => {
        if (d.id === lead.departmentId) {
          const emailedCount = d.emailedCount + 1;
          const pendingCount = Math.max(0, d.pendingCount - 1);
          const completionRate = Math.min(100, Math.round(((d.calledCount + emailedCount) / d.assignedCount) * 100));
          return { ...d, emailedCount, pendingCount, completionRate };
        }
        return d;
      })
    );

    showToast('Email Sent', `Message successfully delivered to ${lead.email}`, 'success');
  };

  const sendBulkEmail = async (leadIds: string[], subject: string, body: string) => {
    const targetLeads = leads.filter(l => leadIds.includes(l.id));
    if (targetLeads.length === 0) return;

    setLeads(prev =>
      prev.map(l =>
        leadIds.includes(l.id)
          ? { ...l, status: 'Emailed', lastActivity: 'Campaign email sent' }
          : l
      )
    );

    setKpiDeltas(prev => ({ ...prev, emails: prev.emails + leadIds.length }));

    const newAct: Activity = {
      id: `act-${Date.now()}`,
      type: 'bulk_email',
      title: `Sent ${leadIds.length} campaign emails`,
      description: `${currentUser.name} sent personalized sequence "${subject}" to ${leadIds.length} recipients.`,
      user: currentUser.name,
      department: currentUser.departmentName || 'General',
      timestamp: 'Just now',
      badgeColor: '#8B5CF6',
    };
    setActivities(prev => [newAct, ...prev]);

    const deptId = targetLeads[0].departmentId;
    setDepartments(prev =>
      prev.map(d => {
        if (d.id === deptId) {
          const emailedCount = d.emailedCount + leadIds.length;
          const pendingCount = Math.max(0, d.pendingCount - leadIds.length);
          const completionRate = Math.min(100, Math.round(((d.calledCount + emailedCount) / d.assignedCount) * 100));
          return { ...d, emailedCount, pendingCount, completionRate };
        }
        return d;
      })
    );

    showToast('Bulk Campaign Sent', `Successfully dispatched ${leadIds.length} emails!`, 'success');
  };

  const updateLeadStatus = async (leadId: string, status: LeadStatus) => {
    const response = await apiService.fetchWithAuth(`${apiService.baseUrl}/api/leads/${leadId}/status`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
    });
    if (!response.ok) { showToast('Status update failed', 'Administrator access is required to change lead status.', 'error'); return; }
    const result = await response.json();
    setLeads(prev => prev.map(row => row.id === leadId ? result.lead : row));
  };

  // -------------------------------------------------------------
  // AI Agent Chat Simulation & Dynamic Requirement Building
  // -------------------------------------------------------------

  const sendMessage = async (sessionId: string, text: string, retryClientMessageId?: string, expectedProposalId?: string) => {
    const clientMessageId = retryClientMessageId || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);

    let targetSessionId = sessionId;
    if (targetSessionId === 'sess-live-init') {
      try {
        const apiRes = await apiService.createNewChat();
        if (apiRes && apiRes.sessionId) {
          targetSessionId = apiRes.sessionId;
          // Update the session in state
          setSessions(prev => prev.map(s => s.id === 'sess-live-init' ? { ...s, id: targetSessionId, requirement: { ...s.requirement, sessionId: targetSessionId, id: `req-${targetSessionId}` } } : s));
          setActiveSessionId(targetSessionId);
          // Migrate any existing messages
          setMessagesBySession(prev => {
            const msgs = prev['sess-live-init'] || [];
            const newPrev = { ...prev };
            delete newPrev['sess-live-init'];
            return { ...newPrev, [targetSessionId]: msgs.map(m => ({ ...m, sessionId: targetSessionId })) };
          });
        }
      } catch (e) {
        console.warn("Failed to create live session on backend", e);
      }
    }

    if (!retryClientMessageId) {
      const userMsg: AgentMessage = {
        id: `msg-${Date.now()}`,
        sessionId: targetSessionId,
        sender: 'user',
        text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        clientMessageId,
      };

      setMessagesBySession(prev => ({
        ...prev,
        [targetSessionId]: [...(prev[targetSessionId] || []), userMsg],
      }));
    }

    const sess = sessions.find(s => s.id === sessionId) || sessions.find(s => s.id === targetSessionId);
    if (!sess) return;

    try {
      const lowerText = text.toLowerCase();
      const isRetrieval = /^(show|view|get|display|list|fetch|see|what are)\b/.test(lowerText) &&
        !/\b(scrape|extract|harvest|crawl|run|new|another)\b/.test(lowerText);

      let reqContext: Requirement | undefined = sess.requirement;
      if (sess.requirement && (sess.requirement.status === 'completed' || sess.requirement.status === 'confirmed') && !isRetrieval) {
        reqContext = {
          ...sess.requirement,
          status: 'collecting',
          completionPercentage: 0,
          datasetId: undefined,
          jobId: undefined as any,
          selectedScript: undefined,
          selectedScriptName: undefined,
          scriptId: undefined,
          scriptName: undefined,
        };
      }

      const request = new AbortController();
      chatRequests.current.set(targetSessionId, request);
      const botResult = await apiService.sendBotMessage(targetSessionId, text, clientMessageId, reqContext, newOnly, expectedProposalId, request.signal);
      chatRequests.current.delete(targetSessionId);
      if (clearedSessions.current.has(targetSessionId)) return;

      if (botResult.is503) {
        const err503Msg: AgentMessage = {
          id: `msg-503-${Date.now()}`,
          sessionId: targetSessionId,
          sender: 'agent',
          text: 'The AI API is not responding. Please try again.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          is503: true,
          failedClientMessageId: clientMessageId,
          failedText: text,
        };
        setMessagesBySession(prev => ({
          ...prev,
          [targetSessionId]: [...(prev[targetSessionId] || []), err503Msg],
        }));
        return;
      }

      if (botResult.error && !botResult.data) {
        showToast('AI Request Failed', botResult.error, 'error');
        return;
      }

      const botRes = botResult.data;
      if (botRes && botRes.reply) {
        if (botRes.records && botRes.records.length > 0) {
          setLeads(prev => {
            const existingIds = new Set(prev.map(l => l.id));
            const newRecords = botRes.records!.filter(r => !existingIds.has(r.id));
            return [...newRecords, ...prev];
          });
        }

        setSessions(prev =>
          prev.map(s => {
            if (s.id !== targetSessionId) return s;
            const updated: Partial<Requirement> = botRes.updatedRequirement || {};
            const mergedReq = {
              ...s.requirement,
              ...updated,
              selectedScript: botRes.recommendedScript || updated.selectedScript || s.requirement.selectedScript,
              industry: Object.prototype.hasOwnProperty.call(updated, 'industry') ? updated.industry || '' : s.requirement.industry,
              location: Object.prototype.hasOwnProperty.call(updated, 'location') ? updated.location || '' : s.requirement.location,
              quantity: updated.quantity || s.requirement.quantity,
              completionPercentage: updated.completionPercentage !== undefined ? updated.completionPercentage : s.requirement.completionPercentage,
              status: updated.status || s.requirement.status,
            };
            return {
              ...s,
              requirement: mergedReq,
              updatedAt: 'Just now',
            };
          })
        );

        const agentMsg: AgentMessage = {
          id: `${botRes.queryId}:agent`,
          sessionId: targetSessionId,
          sender: 'agent',
          text: botRes.reply,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          suggestions: botRes.suggestions && botRes.suggestions.length > 0 ? botRes.suggestions : undefined,
          agentCode: botRes.agentCode,
          handledBy: botRes.handledBy,
          decision: botRes.decision,
          query: botRes.query,
          queryId: botRes.queryId,
          total: botRes.total,
          records: botRes.records,
          showAllDetails: botRes.showAllDetails,
          pendingAction: botRes.pendingAction,
          kb: botRes.kb,
          agentResult: botRes.agentResult,
          collaborationId: botRes.collaborationId,
          collaborationStatus: botRes.collaborationStatus,
          agentsInvolved: botRes.agentsInvolved,
          agentSteps: botRes.agentSteps,
          proposedActions: botRes.proposedActions,
        };

        setMessagesBySession(prev => ({
          ...prev,
          [targetSessionId]: [...(prev[targetSessionId] || []).filter(row => row.id !== agentMsg.id).map(row => ({ ...row, pendingAction: null, proposedActions: [] })), agentMsg],
        }));

        if (botRes.jobId) monitorJob(targetSessionId, botRes.jobId);

        return botRes.jobId || '';
      }
    } catch (err: any) {
      console.warn('Backend bot call error:', err);
    }

    if (clearedSessions.current.has(targetSessionId)) return;
    const fallbackMsg: AgentMessage = {
      id: `msg-${Date.now() + 1}`,
      sessionId,
      sender: 'agent',
      text: 'The AI orchestrator service is currently unavailable or encountered a connection error. Your requirement has been preserved. Please verify that the backend server is running and try again.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      suggestions: ['Retry Request', 'Check System Status'],
    };

    setMessagesBySession(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] || []), fallbackMsg],
    }));
  };

  const retryBotMessage = async (sessionId: string, clientMessageId: string, text: string) => {
    setMessagesBySession(prev => ({
      ...prev,
      [sessionId]: (prev[sessionId] || []).filter(m => !(m.is503 && m.failedClientMessageId === clientMessageId)),
    }));
    await sendMessage(sessionId, text, clientMessageId);
  };

  const confirmBotDecision = async (sessionId: string, decision: 'approve' | 'reject', proposalId?: string) => {
    await sendMessage(sessionId, decision === 'approve' ? 'Yes, run the proposed scrape.' : 'No, do not run it.', undefined, proposalId);
  };

  const clearChat = async () => {
    const deptId = currentUser.departmentId || 'dept-ops';

    // Call the backend API to physically create the session in PostgreSQL
    let newSessionId = `sess-${Date.now()}`;
    let clearedIds: string[] = [];
    try {
      // You may need to call a clear endpoint, but creating a new chat serves as a reset
      const apiRes = await apiService.createNewChat(activeSessionId);
      if (apiRes && apiRes.sessionId) {
        newSessionId = apiRes.sessionId;
        clearedIds = apiRes.clearedSessionIds || [activeSessionId];
      }
    } catch (e) {
      showToast('Could not clear chat', 'The server could not create a new conversation.', 'error');
      return;
    }
    for (const oldId of clearedIds) {
      clearedSessions.current.add(oldId);
      chatRequests.current.get(oldId)?.abort();
      chatRequests.current.delete(oldId);
    }
    for (const timer of monitors.current.values()) clearInterval(timer);
    monitors.current.clear();

    const agent = await agentService.getAgentByDepartment(deptId);
    const newSess: AgentSession = {
      id: newSessionId,
      agentId: agent?.id || 'agent-sales-1',
      departmentId: deptId,
      title: 'Active Request',
      createdAt: 'Just now',
      updatedAt: 'Just now',
      status: 'active',
      requirement: {
        id: `req-${newSessionId}`,
        sessionId: newSessionId,
        departmentId: deptId,
        industry: 'Not specified',
        location: 'Not specified',
        companySize: 'Not specified',
        decisionMakers: [],
        quantity: 0,
        requiredFields: {
          companyName: true,
          contactName: true,
          jobTitle: true,
          email: true,
          phone: true,
          website: true,
        },
        completionPercentage: 0,
        status: 'collecting',
      },
    };

    setSessions([newSess]);
    setActiveSessionId(newSess.id);

    setMessagesBySession({
      [newSess.id]: [
        {
          id: `msg-${Date.now()}`,
          sessionId: newSess.id,
          sender: 'agent',
          text: `Hello ${currentUser.name.split(' ')[0]}. I am your ${currentUser.departmentName} Intelligence Agent. What dataset or leads do you need me to discover today?`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          suggestions: [
            'Scrape Dallas City Bids (Bonfire)',
            'Extract NY State RFPs (DASNY)',
            'Harvest Directory Leads (JWiz)',
            'Scrape State Contracts (NYSCR)',
          ],
        },
      ],
    });
  };

  const confirmRequirementAndGenerate = async (sessionId: string): Promise<string> => {
    const pending = [...(messagesBySession[sessionId] || [])].reverse().find(message => message.pendingAction)?.pendingAction;
    return (await sendMessage(sessionId, 'Yes, run the proposed scrape.', undefined, pending?.proposal?.tool_call_id)) || '';
  };

  // Exact match only: falling back to jobs[0] showed an unrelated job's details
  const getLiveJob = (jobId: string) => {
    return jobs.find(j => j.id === jobId);
  };

  // Dynamically compute department stats from actual leads
  const dynamicDepartments = React.useMemo(() => {
    return departments.map(d => {
      const deptLeads = leads.filter(l => l.departmentId === d.id);
      const count = deptLeads.length;
      const called = deptLeads.filter(l => l.status === 'Called').length;
      const emailed = deptLeads.filter(l => l.status === 'Emailed').length;
      const interested = deptLeads.filter(l => l.status === 'Interested' || l.status === 'Qualified').length;
      const assigned = deptLeads.filter(l => l.assignedTo || l.assignedToName).length;
      const pending = Math.max(0, count - called - emailed - interested);
      const completionRate = count > 0 ? Math.min(100, Math.round(((called + emailed) / count) * 100)) : 0;
      return {
        ...d,
        leadsCount: count,
        assignedCount: assigned,
        calledCount: called,
        emailedCount: emailed,
        interestedCount: interested,
        pendingCount: pending,
        completionRate,
      };
    });
  }, [leads, departments]);

  // Computed Global KPIs from Real Data
  const kpis = {
    totalLeads: leads.length,
    generatedToday: leads.filter(l => l.lastActivity?.includes('now') || l.lastActivity?.includes('Today') || l.createdAt?.includes('now') || l.createdAt?.includes('Today') || l.status === 'New').length,
    callsCompleted: leads.filter(l => l.status === 'Called').length + kpiDeltas.calls,
    emailsSent: leads.filter(l => l.status === 'Emailed').length + kpiDeltas.emails,
    interestedLeads: leads.filter(l => l.status === 'Interested' || l.status === 'Qualified').length + kpiDeltas.interested,
    pendingActions: leads.filter(l => l.status === 'New').length,
  };

  return (
    <DataOpsContext.Provider
      value={{
        currentUser,
        newOnly,
        setNewOnly,
        switchUser,
        switchRole,
        allUsers: authUser ? [currentUser] : [],
        leads,
        datasets,
        activities,
        departments: dynamicDepartments,
        jobs,
        kpis,
        logCall,
        sendEmail,
        sendBulkEmail,
        updateLeadStatus,
        sessions,
        activeSessionId,
        setActiveSessionId,
        messagesBySession,
        sendMessage,
        confirmBotDecision,
        retryBotMessage,
        clearChat,
        confirmRequirementAndGenerate,
        getLiveJob,
        globalSearch,
        setGlobalSearch,
        toasts,
        showToast,
        removeToast,
        notifications,
        markNotificationRead,
        markAllNotificationsRead,
      }}
    >
      {children}
    </DataOpsContext.Provider>
  );
};

export const useDataOps = () => {
  const context = useContext(DataOpsContext);
  if (!context) {
    throw new Error('useDataOps must be used within a DataOpsProvider');
  }
  return context;
};
