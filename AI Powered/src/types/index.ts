export type UserRole = 'admin' | 'user';

export interface User {
  id: string;
  username?: string;
  name: string;
  email?: string;
  role: UserRole;
  roleTitle?: string;
  departmentId?: string;
  departmentName?: string;
  avatar?: string;
  status?: string;
  auth_source?: string;
  builtIn?: boolean;
}

export interface Department {
  id: string;
  name: string;
  code: string;
  description: string;
  leadsCount: number;
  assignedCount: number;
  calledCount: number;
  emailedCount: number;
  interestedCount: number;
  pendingCount: number;
  completionRate: number;
  agentId: string;
  managerName: string;
}

export interface Agent {
  id: string;
  departmentId: string;
  departmentName: string;
  name: string;
  code: string;
  model: string;
  status: 'active' | 'idle' | 'busy';
  description: string;
  capabilities: string[];
}

export interface ProposedAction {
  actionType: string;
  label: string;
  parameters?: Record<string, any>;
  requiresConfirmation?: boolean;
  safeToAutoExecute?: boolean;
}

export interface AgentTaskStep {
  taskId: string;
  agentCode: string;
  purpose: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'SKIPPED' | 'BLOCKED' | string;
  result?: any;
  error?: string | null;
  dependencies?: string[];
  executionOrder?: number;
}

export interface AgentMessage {
  id: string;
  sessionId: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  timestamp: string;
  suggestions?: string[];
  // Layer 6 / 12 / 13 metadata
  agentCode?: string;
  handledBy?: string;
  decision?: string;
  query?: any;
  agentResult?: any;
  collaborationId?: string | null;
  collaborationStatus?: string | null;
  agentsInvolved?: string[];
  agentSteps?: AgentTaskStep[];
  proposedActions?: ProposedAction[];
  clientMessageId?: string;
  is503?: boolean;
  failedClientMessageId?: string;
  failedText?: string;
  records?: Lead[];
  total?: number;
  queryId?: string;
  pendingAction?: any;
  kb?: {
    state?: string;
    available?: boolean;
    hits?: Array<{ chunkId?: string; documentId?: string; title?: string; content?: string; score?: number; [key: string]: any }>;
    [key: string]: any;
  };
}

export interface RequirementFields {
  companyName: boolean;
  contactName: boolean;
  jobTitle: boolean;
  email: boolean;
  phone: boolean;
  website: boolean;
}

export interface Requirement {
  id: string;
  sessionId: string;
  industry: string;
  location: string;
  companySize: string;
  decisionMakers: string[];
  quantity: number;
  requiredFields: RequirementFields;
  completionPercentage: number;
  status: 'collecting' | 'ready_for_confirmation' | 'confirmed' | 'generating' | 'completed' | string;
  datasetId?: string;
  departmentId?: string;
  selectedScript?: string;
  selectedScriptName?: string;
  scriptId?: string;
  scriptName?: string;
  jobId?: string;
  verifiedRecords?: number;
}

export interface AgentSession {
  id: string;
  agentId: string;
  departmentId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  status: 'active' | 'completed' | 'generating' | string;
  requirement: Requirement;
}

export type LeadStatus =
  | 'New'
  | 'Called'
  | 'Emailed'
  | 'Interested'
  | 'Follow Up'
  | 'Not Interested'
  | 'Qualified'
  | 'Contacted'
  | 'Meeting Set'
  | 'Converted';

export interface Lead {
  id: string;
  datasetId: string;
  datasetName: string;
  name: string;
  company: string;
  organizationName?: string;
  title: string;
  email: string;
  phone: string;
  location: string;
  city?: string;
  state?: string;
  status: LeadStatus;
  assignedTo: string;
  assignedToId?: string;
  assignedToName: string;
  departmentId: string;
  departmentName: string;
  lastActivity: string;
  notes?: string;
  nextFollowUp?: string;
  dueAt?: string | null;
  companySize?: string;
  website?: string;
  industry?: string;
  linkedin?: string;
  createdAt: string;
  score?: number;
  priority?: string;
  sourceCode?: string;
  qualityScore?: number;
  emailVerified?: boolean;
  phoneVerified?: boolean;
}

export interface Dataset {
  id: string;
  name: string;
  departmentId: string;
  departmentName: string;
  createdBy: string;
  createdByName: string;
  recordsCount: number;
  verifiedCount: number;
  duplicatesCount: number;
  status: 'Completed' | 'Running' | 'Queued' | 'Failed' | string;
  createdAt: string;
  tags: string[];
  workflowId: string;
  workflowName: string;
}

export interface Activity {
  id: string;
  type: 'call' | 'email' | 'bulk_email' | 'generation' | 'assignment' | 'status_change';
  title: string;
  description: string;
  user: string;
  department: string;
  timestamp: string;
  leadId?: string;
  leadName?: string;
  datasetId?: string;
  badgeColor?: string;
}

export interface Campaign {
  id: string;
  name: string;
  departmentId: string;
  departmentName: string;
  datasetId: string;
  datasetName: string;
  totalLeads: number;
  contactedCount: number;
  interestedCount: number;
  pendingCount: number;
  progress: number;
  status: 'Active' | 'Paused' | 'Completed' | 'Draft';
  startDate: string;
  endDate: string;
  owner: string;
  description?: string;
}

export interface JobLog {
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export interface Job {
  id: string;
  name: string;
  type: string;
  departmentId?: string;
  departmentName?: string;
  progress: number;
  status: 'Queued' | 'Running' | 'Completed' | 'Partial' | 'Failed' | string;
  currentStep: string;
  startedAt: string;
  duration: string;
  recordsFound: number;
  verifiedCount: number;
  duplicatesCount: number;
  errorsCount: number;
  totalTarget: number;
  datasetId?: string;
  scriptId?: string;
  scriptName?: string;
  parameters?: Record<string, any>;
  logs: JobLog[];
}

export interface Script {
  id: string;
  name: string;
  version: string;
  status: 'Active' | 'Beta' | 'Deprecated' | string;
  usedBy?: string[];
  capabilities: string[];
  description: string;
  lastRun?: string;
  successRate?: string;
}

export interface WorkflowStep {
  id: string;
  name: string;
  type: string;
  status: 'completed' | 'running' | 'pending';
  order: number;
  description?: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  departmentId: string;
  steps: WorkflowStep[];
  status: 'Active' | 'Draft';
  lastUsed: string;
}

export interface GanttTask {
  id: string;
  name: string;
  departmentId: string;
  departmentName: string;
  owner: string;
  progress: number;
  startDate: string;
  endDate: string;
  status: 'In Progress' | 'Completed' | 'Pending' | 'Delayed';
  category: 'Data Generation' | 'Lead Assignment' | 'Calling' | 'Email Campaign' | 'Follow-ups';
}

export interface Employee {
  id: string;
  name: string;
  email: string;
  role: string;
  departmentId: string;
  departmentName: string;
  assignedCount: number;
  completedCount: number;
  callsCount: number;
  emailsCount: number;
  interestedCount: number;
  pendingCount: number;
  completionRate: number;
  avatar: string;
  status: 'Active' | 'Away' | 'In Call';
}

export interface SystemStatus {
  backend: boolean;
  database: boolean;
  api: boolean;
  timestamp: number;
  registeredScripts: number;
  error?: string | null;
}

export interface BotChatResponse {
  reply: string;
  suggestions?: string[];
  updatedRequirement?: Requirement;
  recommendedScript?: string | null;
  sessionId?: string;
  decision?: string;
  query?: any;
  queryId?: string;
  total?: number;
  records?: Lead[];
  pendingAction?: any;
  kb?: {
    state?: string;
    available?: boolean;
    hits?: Array<{ chunkId?: string; documentId?: string; title?: string; content?: string; score?: number; [key: string]: any }>;
    [key: string]: any;
  };
  agentCode?: string;
  handledBy?: string;
  agentResult?: any;
  collaborationId?: string | null;
  collaborationStatus?: string | null;
  agentsInvolved?: string[];
  agentSteps?: AgentTaskStep[];
  proposedActions?: ProposedAction[];
  jobId?: string;
}

export interface BotConfirmResponse {
  success: boolean;
  jobId: string;
  scriptId: string;
  datasetId: string | null;
  message: string;
}

export interface LlmUnavailableError {
  code: 'LLM_UNAVAILABLE';
  reason?: 'not_configured' | 'timeout' | 'auth_error' | 'rate_limited' | 'provider_error' | string;
  message: string;
}

export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    reason?: string;
    details?: any;
  };
}

export interface AdminUser {
  id: string;
  name: string;
  username: string;
  role: string;
  status: string;
  auth_source: string;
  builtIn: boolean;
}

export interface AdminRequestItem {
  id: string;
  userId: string;
  userName?: string | null;
  sessionId?: string;
  queryText?: string;
  parameters?: Record<string, any>;
  decision?: string;
  status?: string;
  jobId?: string | null;
  recordsReturned?: number;
  recordsNew?: number;
  recordsUpdated?: number;
  servedAt?: string | null;
  createdAt?: string | null;
}

export interface AdminRequestDetail {
  request: AdminRequestItem;
  job?: {
    id: string;
    name?: string;
    status: string;
    progress: number;
    scriptId: string;
    recordsFound: number;
    verifiedCount: number;
    duplicatesCount: number;
    errorMessage?: string | null;
    startedAt?: string | null;
    completedAt?: string | null;
  } | null;
  transcript: Array<{
    id: string;
    sender: string;
    text: string;
    toolTrace?: any;
    createdAt?: string | null;
  }>;
  rowsServed: Array<{
    leadId: string;
    rank: number;
    company?: string | null;
    contact?: string | null;
    title?: string | null;
  }>;
}

export interface RagStatus {
  state: string;
  available: boolean;
  message?: string;
  documents?: number;
  chunks?: number;
  embeddingModel?: string;
  dim?: number;
  version?: string;
}

export interface RagDocument {
  id: string;
  title?: string;
  content?: string;
  chunksCount?: number;
  createdAt?: string;
  [key: string]: any;
}

