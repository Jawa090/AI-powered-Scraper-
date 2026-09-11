export type UserRole = 'admin' | 'manager' | 'sales' | 'email';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  roleTitle: string;
  departmentId: string;
  departmentName: string;
  avatar: string;
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

export interface AgentMessage {
  id: string;
  sessionId: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  timestamp: string;
  suggestions?: string[];
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
  status: 'collecting' | 'ready_for_confirmation' | 'confirmed' | 'generating' | 'completed';
  datasetId?: string;
  departmentId: string;
}

export interface AgentSession {
  id: string;
  agentId: string;
  departmentId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  status: 'active' | 'completed' | 'generating';
  requirement: Requirement;
}

export type LeadStatus =
  | 'New'
  | 'Called'
  | 'Emailed'
  | 'Interested'
  | 'Follow Up'
  | 'Not Interested'
  | 'Qualified';

export interface Lead {
  id: string;
  datasetId: string;
  datasetName: string;
  name: string;
  company: string;
  title: string;
  email: string;
  phone: string;
  location: string;
  status: LeadStatus;
  assignedTo: string;
  assignedToName: string;
  departmentId: string;
  departmentName: string;
  lastActivity: string;
  notes?: string;
  nextFollowUp?: string;
  companySize?: string;
  website?: string;
  industry?: string;
  linkedin?: string;
  createdAt: string;
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
  status: 'Completed' | 'Running' | 'Queued' | 'Failed';
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
  departmentId: string;
  departmentName: string;
  progress: number;
  status: 'Queued' | 'Running' | 'Completed' | 'Partial' | 'Failed';
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
  status: 'Active' | 'Beta' | 'Deprecated';
  usedBy: string[];
  capabilities: string[];
  description: string;
  lastRun: string;
  successRate: string;
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
