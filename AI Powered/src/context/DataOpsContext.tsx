import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
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
import { MOCK_USERS } from '../mock/users';
import { MOCK_LEADS } from '../mock/leads';
import { MOCK_DATASETS } from '../mock/datasets';
import { MOCK_ACTIVITIES } from '../mock/activities';
import { MOCK_DEPARTMENTS } from '../mock/departments';
import { MOCK_JOBS } from '../mock/jobs';
import { agentService } from '../services/agent.service';
import { apiService } from '../services/api.service';

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
  setActiveSessionId: (id: string) => void;
  messagesBySession: Record<string, AgentMessage[]>;
  sendMessage: (sessionId: string, text: string) => Promise<void>;
  createSession: (departmentId?: string, title?: string) => Promise<AgentSession>;
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
  const [currentUser, setCurrentUser] = useState<User>(MOCK_USERS[0]); // Ahmed (Sales)
  const [leads, setLeads] = useState<Lead[]>(MOCK_LEADS);
  const [datasets, setDatasets] = useState<Dataset[]>(MOCK_DATASETS);
  const [activities, setActivities] = useState<Activity[]>(MOCK_ACTIVITIES);
  const [departments, setDepartments] = useState<Department[]>(MOCK_DEPARTMENTS);
  const [jobs, setJobs] = useState<Job[]>(MOCK_JOBS);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [globalSearch, setGlobalSearch] = useState('');

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

  // Notifications
  const [notifications, setNotifications] = useState([
    { id: 'notif-1', title: 'Dallas Bonfire Harvested', desc: 'Dallas Bonfire Hub scraper extracted 22 open municipal procurement opportunities.', time: '10m ago', read: false },
    { id: 'notif-2', title: 'JWiz Verified Leads Ready', desc: 'Extracted commercial contractors with phone numbers and validated emails.', time: '40m ago', read: false },
    { id: 'notif-3', title: 'DASNY RFP Bids Synced', desc: '6 architectural and construction bid opportunities captured.', time: '1h ago', read: false },
    { id: 'notif-4', title: 'NYSCR State Contract Reporter', desc: '5 open state agency contracts harvested with contact emails.', time: '2h ago', read: true },
  ]);

  useEffect(() => {
    // Load initial sessions with a clean active session to prevent mock contamination
    agentService.getSessions().then(sess => {
      const initialCleanSession: AgentSession = {
        id: 'sess-live-init',
        agentId: 'agent-sales-1',
        departmentId: 'dept-sales-1',
        title: 'New Autonomous Request',
        createdAt: 'Just now',
        updatedAt: 'Just now',
        status: 'active',
        requirement: {
          id: 'req-live-init',
          sessionId: 'sess-live-init',
          departmentId: 'dept-sales-1',
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
      setSessions([initialCleanSession, ...sess]);
      setActiveSessionId('sess-live-init');
    });

    // Sync live datasets, jobs, and leads from FastAPI backend
    apiService.getHealth().then(healthy => {
      if (healthy) {
        apiService.getDatasets().then(ds => {
          if (ds && ds.length > 0) {
            setDatasets(ds);
          }
        });
        apiService.getJobs().then(jb => {
          if (jb && jb.length > 0) {
            setJobs(jb);
          }
        });
        apiService.getLeads().then(ld => {
          if (ld && ld.length > 0) {
            setLeads(ld);
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
  }, []);

  const showToast = (title: string, message: string, type: ToastMessage['type'] = 'success') => {
    const id = `toast-${Date.now()}-${Math.random()}`;
    setToasts(prev => [...prev, { id, title, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4500);
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

  const switchUser = (userId: string) => {
    const user = MOCK_USERS.find(u => u.id === userId);
    if (user) {
      setCurrentUser(user);
      showToast('Switched Profile', `Active user is now ${user.name} (${user.roleTitle})`, 'info');
    }
  };

  const switchRole = (role: UserRole) => {
    const user = MOCK_USERS.find(u => u.role === role) || MOCK_USERS[0];
    setCurrentUser(user);
    showToast('Role Switched', `Now operating as ${user.role.toUpperCase()}: ${user.name}`, 'info');
  };

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
      title: `Call logged with ${lead.name}`,
      description: `${currentUser.name} completed call with ${lead.name} (${lead.company}). Outcome: ${outcome}.${notes ? ` Note: "${notes}"` : ''}`,
      user: currentUser.name,
      department: currentUser.departmentName,
      timestamp: 'Just now',
      leadId: lead.id,
      leadName: lead.name,
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
      title: `Email sent to ${lead.name}`,
      description: `${currentUser.name} sent "${subject}" to ${lead.email} (${lead.company}).`,
      user: currentUser.name,
      department: currentUser.departmentName,
      timestamp: 'Just now',
      leadId: lead.id,
      leadName: lead.name,
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
      department: currentUser.departmentName,
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
    const lead = leads.find(l => l.id === leadId);
    if (!lead) return;

    setLeads(prev =>
      prev.map(l =>
        l.id === leadId
          ? { ...l, status, lastActivity: `Status updated to ${status}` }
          : l
      )
    );

    showToast('Status Updated', `${lead.name} is now marked as "${status}".`, 'info');
  };

  // -------------------------------------------------------------
  // AI Agent Chat Simulation & Dynamic Requirement Building
  // -------------------------------------------------------------
  const [messagesBySession, setMessagesBySession] = useState<Record<string, AgentMessage[]>>({
    'sess-live-init': [
      {
        id: 'msg-init-live',
        sessionId: 'sess-live-init',
        sender: 'agent',
        text: `Welcome! I am your Autonomous Data Operations Intelligence Bot. I am connected directly to 4 live production scraping engines:

1. 🏛️ Dallas City Hall Bonfire Hub (City procurement bids, RFPs & commodity contracts)
2. 🏢 DASNY RFP Opportunities (State of New York Dormitory Authority construction & architectural RFPs)
3. 📒 JWiz Directory (Commercial contractors, electricians, plumbers & business contacts)
4. 📜 NYSCR State Contract Reporter (New York open government & agency contracts)

Which scraper engine would you like to target today, or what specific type of leads/bids do you need?`,
        timestamp: 'Just now',
        suggestions: [
          'Dallas City Hall Bonfire',
          'DASNY NY RFP Bids',
          'JWiz Commercial Directory',
          'NYSCR State Contracts',
        ],
      },
    ],
    'sess-bonfire': [
      {
        id: 'msg-init-1',
        sessionId: 'sess-bonfire',
        sender: 'agent',
        text: `Welcome! I am your Autonomous Data Operations Intelligence Bot. I am connected directly to 4 live production scraping engines:

1. 🏛️ Dallas City Hall Bonfire Hub (City procurement bids, RFPs & commodity contracts)
2. 🏢 DASNY RFP Opportunities (State of New York Dormitory Authority construction & architectural RFPs)
3. 📒 JWiz Directory (Commercial contractors, electricians, plumbers & business contacts)
4. 📜 NYSCR State Contract Reporter (New York open government & agency contracts)

Which scraper engine would you like to target today, or what specific type of leads/bids do you need?`,
        timestamp: 'Just now',
        suggestions: [
          'Dallas City Hall Bonfire',
          'DASNY NY RFP Bids',
          'JWiz Commercial Directory',
          'NYSCR State Contracts',
        ],
      },
    ],
  });

  const sendMessage = async (sessionId: string, text: string) => {
    const userMsg: AgentMessage = {
      id: `msg-${Date.now()}`,
      sessionId,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessagesBySession(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] || []), userMsg],
    }));

    // Find session and requirement
    const sess = sessions.find(s => s.id === sessionId);
    if (!sess) return;

    // Call FastAPI bot endpoint
    try {
      // Context hygiene:
      // If the session requirement is already completed or confirmed, but user is asking for a new search
      // ("I need...", "Find...", "Scrape..."), do not contaminate the new request with stale datasetId or completed status.
      // For follow-up retrieval requests ("Show me...", "View...", "Give me..."), preserve datasetId and completed status.
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

      const botRes = await apiService.sendBotMessage(sessionId, text, reqContext);
      if (botRes && botRes.reply) {
        setSessions(prev =>
          prev.map(s => (s.id === sessionId ? { ...s, requirement: botRes.updatedRequirement || s.requirement, updatedAt: 'Just now' } : s))
        );

        const agentMsg: AgentMessage = {
          id: `msg-${Date.now() + 1}`,
          sessionId,
          sender: 'agent',
          text: botRes.reply,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          suggestions: botRes.suggestions && botRes.suggestions.length > 0 ? botRes.suggestions : undefined,
          agentCode: botRes.agentCode,
          handledBy: botRes.handledBy,
          decision: botRes.decision,
          query: botRes.query,
          agentResult: botRes.agentResult,
          collaborationId: botRes.collaborationId,
          collaborationStatus: botRes.collaborationStatus,
          agentsInvolved: botRes.agentsInvolved,
          agentSteps: botRes.agentSteps,
          proposedActions: botRes.proposedActions,
        };

        setMessagesBySession(prev => ({
          ...prev,
          [sessionId]: [...(prev[sessionId] || []), agentMsg],
        }));

        // If an autonomous scraper job was triggered directly by the command
        if (botRes.jobId) {
          const liveJobId = botRes.jobId;
          const targetScript = botRes.recommendedScript || 'Scraper';
          showToast('Extraction Started', `Autonomous workflow initiated using ${targetScript.toUpperCase()}.`, 'info');

          // Ensure session requirement tracks the job in generating state
          setSessions(prev =>
            prev.map(s => {
              if (s.id === sessionId) {
                return {
                  ...s,
                  requirement: {
                    ...(botRes.updatedRequirement || s.requirement),
                    jobId: liveJobId,
                    status: 'generating',
                    completionPercentage: Math.max(25, Math.min(95, botRes.updatedRequirement?.completionPercentage || 30)),
                  },
                };
              }
              return s;
            })
          );

          // Fetch job details and add to jobs state
          apiService.getJob(liveJobId).then(liveJob => {
            if (liveJob) {
              setJobs(prev => [liveJob, ...prev.filter(j => j.id !== liveJobId)]);
            }
          });

          // Poll job progress until completion
          const pollTimer = setInterval(async () => {
            const liveJob = await apiService.getJob(liveJobId);
            if (liveJob) {
              setJobs(prev => prev.map(j => (j.id === liveJobId ? liveJob : j)));

              if (liveJob.status === 'Running' || liveJob.status === 'In Progress') {
                const prog = Math.max(25, Math.min(95, liveJob.progress || 35));
                setSessions(prev =>
                  prev.map(s => {
                    if (s.id === sessionId) {
                      return {
                        ...s,
                        requirement: {
                          ...s.requirement,
                          jobId: liveJobId,
                          status: 'generating',
                          completionPercentage: prog,
                        },
                      };
                    }
                    return s;
                  })
                );
              } else if (liveJob.status === 'Completed' || liveJob.status === 'Failed' || liveJob.status === 'Blocked') {
                clearInterval(pollTimer);
                if (liveJob.status === 'Completed') {
                  const [updatedLeads, updatedDatasets] = await Promise.all([
                    apiService.getLeads(),
                    apiService.getDatasets(),
                  ]);
                  if (updatedLeads && updatedLeads.length > 0) {
                    setLeads(updatedLeads);
                  }
                  if (updatedDatasets && updatedDatasets.length > 0) {
                    setDatasets(updatedDatasets);
                  }

                  const verifiedCount = liveJob.recordsFound || (updatedLeads ? updatedLeads.length : 0);
                  const scriptName = liveJob.name || targetScript.toUpperCase();

                  setSessions(prev =>
                    prev.map(s => {
                      if (s.id === sessionId) {
                        return {
                          ...s,
                          requirement: {
                            ...s.requirement,
                            jobId: liveJobId,
                            status: 'completed',
                            completionPercentage: 100,
                            quantity: verifiedCount || s.requirement.quantity,
                            verifiedRecords: verifiedCount,
                          },
                        };
                      }
                      return s;
                    })
                  );

                  const compMsg: AgentMessage = {
                    id: `msg-completed-${Date.now()}`,
                    sessionId,
                    sender: 'agent',
                    text: `**${scriptName}** extraction completed.\n\nStatus: **COMPLETED**\nVerified Records: **${verifiedCount}**\n\nAll requested records have been verified and indexed.`,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    agentCode: 'data',
                    handledBy: 'ScraperExecutionEngine',
                    proposedActions: [
                      {
                        actionType: 'view_results',
                        label: 'View Results',
                        parameters: { jobId: liveJobId, datasetId: liveJob.datasetId },
                      },
                    ],
                    suggestions: ['View Harvested Leads', 'Export CSV', 'Filter by Contact Info'],
                  };
                  setMessagesBySession(prev => ({
                    ...prev,
                    [sessionId]: [...(prev[sessionId] || []), compMsg],
                  }));

                  showToast('Dataset Ready!', `${scriptName} finished with ${verifiedCount} verified records!`, 'success');
                } else if (liveJob.status === 'Failed') {
                  const scriptName = liveJob.name || targetScript.toUpperCase();
                  setSessions(prev =>
                    prev.map(s => {
                      if (s.id === sessionId) {
                        return {
                          ...s,
                          requirement: {
                            ...s.requirement,
                            jobId: liveJobId,
                            status: 'failed',
                            completionPercentage: 0,
                          },
                        };
                      }
                      return s;
                    })
                  );

                  const failMsg: AgentMessage = {
                    id: `msg-failed-${Date.now()}`,
                    sessionId,
                    sender: 'agent',
                    text: `**${scriptName}** extraction could not be completed right now.\n\nStatus: **FAILED**\n\nThe extraction job encountered an error during execution.`,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    agentCode: 'data',
                    handledBy: 'ScraperExecutionEngine',
                    proposedActions: [
                      {
                        actionType: 'retry_scraper',
                        label: 'Retry / View Details',
                        parameters: { jobId: liveJobId, scriptId: liveJob.scriptId },
                      },
                    ],
                    suggestions: ['Retry Scraper', 'Show Recent Extraction Jobs'],
                  };
                  setMessagesBySession(prev => ({
                    ...prev,
                    [sessionId]: [...(prev[sessionId] || []), failMsg],
                  }));

                  showToast('Extraction Failed', `Job ${liveJobId} failed. Check execution logs.`, 'error');
                } else if (liveJob.status === 'Blocked') {
                  const scriptName = liveJob.name || targetScript.toUpperCase();
                  setSessions(prev =>
                    prev.map(s => {
                      if (s.id === sessionId) {
                        return {
                          ...s,
                          requirement: {
                            ...s.requirement,
                            jobId: liveJobId,
                            status: 'blocked',
                            completionPercentage: 0,
                          },
                        };
                      }
                      return s;
                    })
                  );

                  const blockedMsg: AgentMessage = {
                    id: `msg-blocked-${Date.now()}`,
                    sessionId,
                    sender: 'agent',
                    text: `**${scriptName}** extraction is **BLOCKED**.\n\nRequired credentials or environment configurations are missing.`,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    agentCode: 'data',
                    handledBy: 'ScraperExecutionEngine',
                    proposedActions: [],
                    suggestions: ['Configure Credentials', 'Select Different Engine'],
                  };
                  setMessagesBySession(prev => ({
                    ...prev,
                    [sessionId]: [...(prev[sessionId] || []), blockedMsg],
                  }));

                  showToast('Extraction Blocked', `Job ${liveJobId} is blocked: Credentials required.`, 'warning');
                }
              }
            }
          }, 1500);
        }

        return;
      }
    } catch (err) {
      console.warn('Backend bot call error:', err);
    }

    // Backend unavailable / connection error fallback:
    // Preserve existing requirement without inventing category/location/industry/script decisions
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

  const createSession = async (departmentId?: string, title?: string): Promise<AgentSession> => {
    const deptId = departmentId || currentUser.departmentId;
    const newSess = await agentService.createSession(deptId, title);
    setSessions(prev => [newSess, ...prev]);
    setActiveSessionId(newSess.id);

    setMessagesBySession(prev => ({
      ...prev,
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
    }));

    return newSess;
  };

  const confirmRequirementAndGenerate = async (sessionId: string): Promise<string> => {
    const sess = sessions.find(s => s.id === sessionId);
    if (!sess) return 'req-texas-const';

    let liveJobId = '';
    let liveDatasetId = '';

    // Trigger real scraper in FastAPI backend
    try {
      const confirmRes = await apiService.confirmBotRequirement(sessionId, sess.requirement);
      if (confirmRes && confirmRes.success && confirmRes.jobId) {
        liveJobId = confirmRes.jobId;
        liveDatasetId = confirmRes.datasetId;
      }
    } catch (err) {
      console.warn('Backend confirm error, falling back to simulation:', err);
    }

    const jobId = liveJobId || `job-${Date.now().toString().slice(-4)}`;
    const datasetId = liveDatasetId || `ds-${Date.now().toString().slice(-4)}`;

    const newJob: Job = {
      id: jobId,
      name: `${sess.requirement.industry} Pipeline`,
      type: 'Data Generation & Verification',
      departmentId: sess.departmentId,
      departmentName: currentUser.departmentName,
      progress: 10,
      status: 'Running',
      currentStep: 'Initializing autonomous scraper engine',
      startedAt: 'Just now',
      duration: '00:05',
      recordsFound: 0,
      verifiedCount: 0,
      duplicatesCount: 0,
      errorsCount: 0,
      totalTarget: sess.requirement.quantity || 25,
      datasetId,
      logs: [
        { timestamp: '00:01', level: 'info', message: 'Requirement confirmed by user. Starting extraction pipeline.' },
        { timestamp: '00:05', level: 'info', message: `Targeting: ${sess.requirement.industry} in ${sess.requirement.location}.` },
      ],
    };

    setJobs(prev => [newJob, ...prev]);

    setSessions(prev =>
      prev.map(s =>
        s.id === sessionId
          ? {
              ...s,
              status: 'generating',
              requirement: { ...s.requirement, status: 'generating', datasetId },
            }
          : s
      )
    );

    showToast('Extraction Started', `Autonomous workflow initiated for ${sess.requirement.quantity || 25} records.`, 'info');

    // If live backend job exists, poll real status and fetch records!
    if (liveJobId) {
      const pollInterval = setInterval(async () => {
        const liveJob = await apiService.getJob(liveJobId);
        if (liveJob) {
          setJobs(prev => prev.map(j => (j.id === liveJobId ? liveJob : j)));

          if (liveJob.status === 'Running' || liveJob.status === 'In Progress') {
            const prog = Math.max(25, Math.min(95, liveJob.progress || 35));
            setSessions(prev =>
              prev.map(s =>
                s.id === sessionId
                  ? {
                      ...s,
                      requirement: {
                        ...s.requirement,
                        jobId: liveJobId,
                        status: 'generating',
                        completionPercentage: prog,
                      },
                    }
                  : s
              )
            );
          } else if (liveJob.status === 'Completed' || liveJob.status === 'Failed') {
            clearInterval(pollInterval);
            if (liveJob.status === 'Completed') {
              const [newLeads, newDatasets] = await Promise.all([
                apiService.getLeads(liveDatasetId),
                apiService.getDatasets(),
              ]);

              if (newLeads && newLeads.length > 0) {
                setLeads(prev => [...newLeads, ...prev]);
                setKpiDeltas(prev => ({
                  ...prev,
                  generated: prev.generated + newLeads.length,
                }));
              }
              if (newDatasets && newDatasets.length > 0) {
                const foundDs = newDatasets.find(d => d.id === liveDatasetId);
                if (foundDs) {
                  setDatasets(prev => [foundDs, ...prev.filter(d => d.id !== liveDatasetId)]);
                }
              }

              const verifiedCount = liveJob.recordsFound || (newLeads ? newLeads.length : 0);
              setSessions(prev =>
                prev.map(s =>
                  s.id === sessionId
                    ? {
                        ...s,
                        status: 'completed',
                        requirement: {
                          ...s.requirement,
                          jobId: liveJobId,
                          status: 'completed',
                          completionPercentage: 100,
                          quantity: verifiedCount || s.requirement.quantity,
                          verifiedRecords: verifiedCount,
                        },
                      }
                    : s
                )
              );

              showToast('Dataset Ready!', `${sess.requirement.industry} scraper finished with ${verifiedCount} verified records!`, 'success');
            } else if (liveJob.status === 'Failed') {
              setSessions(prev =>
                prev.map(s =>
                  s.id === sessionId
                    ? {
                        ...s,
                        status: 'failed',
                        requirement: {
                          ...s.requirement,
                          jobId: liveJobId,
                          status: 'failed',
                          completionPercentage: 0,
                        },
                      }
                    : s
                )
              );
              showToast('Extraction Failed', `Job ${liveJobId} encountered an error.`, 'error');
            } else if (liveJob.status === 'Blocked') {
              setSessions(prev =>
                prev.map(s =>
                  s.id === sessionId
                    ? {
                        ...s,
                        status: 'blocked',
                        requirement: {
                          ...s.requirement,
                          jobId: liveJobId,
                          status: 'blocked',
                          completionPercentage: 0,
                        },
                      }
                    : s
                )
              );
              showToast('Extraction Blocked', `Job ${liveJobId} is blocked: Credentials required.`, 'warning');
            }
          }
        }
      }, 1200);
    } else {
      // No real backend job ID returned — do NOT simulate fake data.
      // Mark the placeholder job as Failed and inform the user.
      showBackendUnavailableWarning(jobId, sessionId);
    }

    return jobId;
  };

  /**
   * Called when backend returns no live job ID (backend unreachable or confirm failed).
   * Updates job state to Failed and shows a clear error — does NOT generate fake data.
   */
  const showBackendUnavailableWarning = (jobId: string, sessionId: string) => {
    setJobs(prev =>
      prev.map(j =>
        j.id === jobId
          ? {
              ...j,
              status: 'Failed',
              progress: 0,
              currentStep: 'Backend unavailable — could not start extraction job',
            }
          : j
      )
    );
    setSessions(prev =>
      prev.map(s =>
        s.id === sessionId
          ? { ...s, requirement: { ...s.requirement, status: 'failed', completionPercentage: 0 } }
          : s
      )
    );
    showToast(
      'Backend Unavailable',
      'Could not reach the FastAPI backend to start extraction. No data was generated.',
      'error'
    );
  };

  const getLiveJob = (jobId: string) => {
    return jobs.find(j => j.id === jobId) || jobs[0];
  };

  // Dynamically compute department stats from actual leads
  const dynamicDepartments = React.useMemo(() => {
    return departments.map(d => {
      const deptLeads = leads.filter(l => l.departmentId === d.id);
      const called = deptLeads.filter(l => l.status === 'Called').length;
      const emailed = deptLeads.filter(l => l.status === 'Emailed').length;
      const interested = deptLeads.filter(l => l.status === 'Interested' || l.status === 'Qualified').length;
      const count = deptLeads.length > 0 ? deptLeads.length : d.leadsCount;
      const assigned = deptLeads.filter(l => l.assignedToId).length || count;
      const pending = Math.max(0, count - called - emailed - interested);
      const completionRate = count > 0 ? Math.min(100, Math.round(((called + emailed) / count) * 100)) : d.completionRate;
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
        switchUser,
        switchRole,
        allUsers: MOCK_USERS,
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
        createSession,
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
