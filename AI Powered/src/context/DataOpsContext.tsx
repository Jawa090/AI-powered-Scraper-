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
  const [activeSessionId, setActiveSessionId] = useState<string>('sess-bonfire');

  // Notifications
  const [notifications, setNotifications] = useState([
    { id: 'notif-1', title: 'Dallas Bonfire Harvested', desc: 'Dallas Bonfire Hub scraper extracted 22 open municipal procurement opportunities.', time: '10m ago', read: false },
    { id: 'notif-2', title: 'JWiz Verified Leads Ready', desc: 'Extracted commercial contractors with phone numbers and validated emails.', time: '40m ago', read: false },
    { id: 'notif-3', title: 'DASNY RFP Bids Synced', desc: '6 architectural and construction bid opportunities captured.', time: '1h ago', read: false },
    { id: 'notif-4', title: 'NYSCR State Contract Reporter', desc: '5 open state agency contracts harvested with contact emails.', time: '2h ago', read: true },
  ]);

  useEffect(() => {
    // Load initial sessions
    agentService.getSessions().then(sess => {
      setSessions(sess);
      if (sess.length > 0 && !activeSessionId) {
        setActiveSessionId(sess[0].id);
      }
    });

    // Sync live datasets, jobs, and leads from FastAPI backend
    apiService.getHealth().then(healthy => {
      if (healthy) {
        apiService.getDatasets().then(ds => {
          if (ds && ds.length > 0) {
            setDatasets(prev => {
              const existingIds = new Set(prev.map(d => d.id));
              const newItems = ds.filter(d => !existingIds.has(d.id));
              return [...newItems, ...prev];
            });
          }
        });
        apiService.getJobs().then(jb => {
          if (jb && jb.length > 0) {
            setJobs(prev => {
              const existingIds = new Set(prev.map(j => j.id));
              const newItems = jb.filter(j => !existingIds.has(j.id));
              return [...newItems, ...prev];
            });
          }
        });
        apiService.getLeads().then(ld => {
          if (ld && ld.length > 0) {
            setLeads(prev => {
              const existingIds = new Set(prev.map(l => l.id));
              const newItems = ld.filter(l => !existingIds.has(l.id));
              return [...newItems, ...prev];
            });
            setKpiDeltas(prev => ({
              ...prev,
              generated: prev.generated + ld.length,
            }));
            showToast(
              'FastAPI Connected',
              `Loaded ${ld.length} live records from autonomous scrapers.`,
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
      const botRes = await apiService.sendBotMessage(sessionId, text, sess.requirement);
      if (botRes && botRes.reply) {
        setSessions(prev =>
          prev.map(s => (s.id === sessionId ? { ...s, requirement: botRes.updatedRequirement, updatedAt: 'Just now' } : s))
        );

        const agentMsg: AgentMessage = {
          id: `msg-${Date.now() + 1}`,
          sessionId,
          sender: 'agent',
          text: botRes.reply,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          suggestions: botRes.suggestions && botRes.suggestions.length > 0 ? botRes.suggestions : undefined,
        };

        setMessagesBySession(prev => ({
          ...prev,
          [sessionId]: [...(prev[sessionId] || []), agentMsg],
        }));
        return;
      }
    } catch (err) {
      console.warn('Backend bot call error, using local fallback:', err);
    }

    // Local fallback
    const lower = text.toLowerCase();
    const req = { ...sess.requirement };
    let botResponse = '';
    let suggestions: string[] = [];

    if (lower.includes('construction') || lower.includes('texas')) {
      req.industry = 'Commercial Construction';
      req.location = 'Texas, USA';
      req.completionPercentage = 40;
      botResponse = 'Got it. Commercial construction in Texas. What company size should we focus on?';
      suggestions = ['10 to 50 employees', '50 to 500 employees', '500+ employees'];
    } else if (lower.includes('saas') || lower.includes('software') || lower.includes('tech')) {
      req.industry = 'B2B SaaS / Software';
      req.location = lower.includes('usa') || lower.includes('us') ? 'United States' : 'North America';
      req.completionPercentage = 40;
      botResponse = 'Excellent. Targeting B2B SaaS companies. Which executive roles should we extract?';
      suggestions = ['Founders & CEOs', 'VP of Sales & Marketing', 'CTO & VP Engineering'];
    } else if (lower.includes('50') || lower.includes('size') || lower.includes('employees')) {
      req.companySize = text;
      req.completionPercentage = Math.max(req.completionPercentage, 60);
      botResponse = `Understood. Company size bracket set to ${text}. Which specific decision makers should I target?`;
      suggestions = ['Owners and CEOs', 'VP Operations', 'Managing Partners'];
    } else if (lower.includes('ceo') || lower.includes('owner') || lower.includes('founder') || lower.includes('decision')) {
      req.decisionMakers = [text];
      req.completionPercentage = Math.max(req.completionPercentage, 80);
      botResponse = 'Decision maker criteria locked in. How many verified lead records do you require?';
      suggestions = ['500 leads', '1,000 leads', '2,000 leads'];
    } else if (lower.match(/\d+/) || lower.includes('leads') || lower.includes('quantity')) {
      const num = parseInt(text.replace(/[^0-9]/g, '')) || 1000;
      req.quantity = num;
      req.completionPercentage = 100;
      req.status = 'ready_for_confirmation';
      botResponse = `All requirements fulfilled! ${num.toLocaleString()} leads specification is complete. Please verify the requirement summary on the right and click "Confirm & Generate Data" to initiate the autonomous extraction pipeline.`;
    } else {
      req.completionPercentage = Math.min(100, req.completionPercentage + 25);
      if (req.completionPercentage >= 100) {
        req.status = 'ready_for_confirmation';
        botResponse = 'Thank you. I have all necessary parameters. Your requirement is 100% complete and ready for confirmation.';
      } else {
        botResponse = `Understood. I have logged "${text}". How many records would you like generated?`;
        suggestions = ['1,000 records', '2,000 records'];
      }
    }

    setSessions(prev =>
      prev.map(s => (s.id === sessionId ? { ...s, requirement: req, updatedAt: 'Just now' } : s))
    );

    setTimeout(() => {
      const agentMsg: AgentMessage = {
        id: `msg-${Date.now() + 1}`,
        sessionId,
        sender: 'agent',
        text: botResponse,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        suggestions: suggestions.length > 0 ? suggestions : undefined,
      };

      setMessagesBySession(prev => ({
        ...prev,
        [sessionId]: [...(prev[sessionId] || []), agentMsg],
      }));
    }, 650);
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

          if (liveJob.status === 'Completed' || liveJob.status === 'Failed') {
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
              showToast('Dataset Ready!', `${sess.requirement.industry} scraper finished with ${liveJob.recordsFound} verified records!`, 'success');
            }
          }
        }
      }, 1200);
    } else {
      simulateJobProgression(jobId, datasetId, sess.requirement);
    }

    return jobId;
  };

  const simulateJobProgression = (jobId: string, datasetId: string, requirement: Requirement) => {
    const steps = [
      { step: 'Understanding requirement', progress: 15, found: 200, verified: 180 },
      { step: 'Selecting workflow', progress: 28, found: 520, verified: 480 },
      { step: 'Collecting companies', progress: 45, found: 890, verified: 810 },
      { step: 'Finding contacts', progress: 62, found: 1320, verified: 1210 },
      { step: 'Finding emails', progress: 80, found: 1680, verified: 1510 },
      { step: 'Verifying data', progress: 92, found: 1842, verified: 1620 },
      { step: 'Deduplicating', progress: 97, found: 1950, verified: 1720 },
      { step: 'Preparing dataset', progress: 100, found: requirement.quantity || 1000, verified: Math.round((requirement.quantity || 1000) * 0.96) },
    ];

    let currentStepIdx = 0;
    const interval = setInterval(() => {
      currentStepIdx++;
      if (currentStepIdx < steps.length) {
        const s = steps[currentStepIdx];
        setJobs(prev =>
          prev.map(j =>
            j.id === jobId
              ? {
                  ...j,
                  progress: s.progress,
                  currentStep: s.step,
                  recordsFound: s.found,
                  verifiedCount: s.verified,
                  duplicatesCount: Math.round(s.found * 0.03),
                  errorsCount: Math.round(s.found * 0.01),
                  status: s.progress === 100 ? 'Completed' : 'Running',
                  logs: [
                    ...j.logs,
                    {
                      timestamp: `0${Math.floor(currentStepIdx / 2)}:${(currentStepIdx * 12) % 60}`,
                      level: 'info',
                      message: `Step "${s.step}" completed. ${s.found} records processed.`,
                    },
                  ],
                }
              : j
          )
        );
      } else {
        clearInterval(interval);
        // Finalize Dataset
        const targetQty = requirement.quantity || 1000;
        const newDataset: Dataset = {
          id: datasetId,
          name: `${requirement.location} ${requirement.industry}`,
          departmentId: requirement.departmentId,
          departmentName: currentUser.departmentName,
          createdBy: currentUser.id,
          createdByName: currentUser.name,
          recordsCount: targetQty,
          verifiedCount: Math.round(targetQty * 0.96),
          duplicatesCount: 28,
          status: 'Completed',
          createdAt: 'Just now',
          tags: [requirement.industry, requirement.location, 'Generated Today'],
          workflowId: 'wf-const-lead-gen',
          workflowName: 'Autonomous Intelligence Flow',
        };

        setDatasets(prev => [newDataset, ...prev]);

        // Add 5 fresh leads tied to this new dataset
        const generatedLeads: Lead[] = [
          {
            id: `lead-gen-${Date.now()}-1`,
            datasetId,
            datasetName: newDataset.name,
            name: 'Christopher Vance',
            company: 'Vance & Associates Construction',
            title: 'Chief Executive Officer',
            email: 'cvance@vancebuilt.example.com',
            phone: '+1 (512) 890-2109',
            location: requirement.location || 'Austin, TX',
            status: 'New',
            assignedTo: currentUser.id,
            assignedToName: currentUser.name,
            departmentId: currentUser.departmentId,
            departmentName: currentUser.departmentName,
            lastActivity: 'Generated just now',
            companySize: '180 employees',
            website: 'https://vancebuilt.example.com',
            industry: requirement.industry,
            createdAt: 'Just now',
          },
          {
            id: `lead-gen-${Date.now()}-2`,
            datasetId,
            datasetName: newDataset.name,
            name: 'Patricia Morales',
            company: 'Lone Star Commercial Works',
            title: 'Owner & Managing Director',
            email: 'pmorales@lonestarcommercial.example.com',
            phone: '+1 (214) 773-1990',
            location: requirement.location || 'Dallas, TX',
            status: 'New',
            assignedTo: currentUser.id,
            assignedToName: currentUser.name,
            departmentId: currentUser.departmentId,
            departmentName: currentUser.departmentName,
            lastActivity: 'Generated just now',
            companySize: '95 employees',
            website: 'https://lonestarcommercial.example.com',
            industry: requirement.industry,
            createdAt: 'Just now',
          },
          {
            id: `lead-gen-${Date.now()}-3`,
            datasetId,
            datasetName: newDataset.name,
            name: 'Jonathan Sterling',
            company: 'Apex Industrial Structures',
            title: 'President & Founder',
            email: 'jsterling@apexstructures.example.com',
            phone: '+1 (713) 440-8812',
            location: requirement.location || 'Houston, TX',
            status: 'New',
            assignedTo: currentUser.id,
            assignedToName: currentUser.name,
            departmentId: currentUser.departmentId,
            departmentName: currentUser.departmentName,
            lastActivity: 'Generated just now',
            companySize: '310 employees',
            website: 'https://apexstructures.example.com',
            industry: requirement.industry,
            createdAt: 'Just now',
          },
        ];

        setLeads(prev => [...generatedLeads, ...prev]);

        // Update KPIs
        setKpiDeltas(prev => ({
          ...prev,
          generated: prev.generated + targetQty,
        }));

        // Add Activity
        const newAct: Activity = {
          id: `act-${Date.now()}`,
          type: 'generation',
          title: `${currentUser.departmentName} generated ${targetQty} leads`,
          description: `Dataset "${newDataset.name}" generated with ${Math.round(targetQty * 0.96)} verified records.`,
          user: currentUser.name,
          department: currentUser.departmentName,
          timestamp: 'Just now',
          datasetId,
          badgeColor: '#2D4351',
        };
        setActivities(prev => [newAct, ...prev]);

        showToast('Dataset Ready!', `${newDataset.name} generated ${targetQty} leads successfully.`, 'success');
      }
    }, 1200);
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
