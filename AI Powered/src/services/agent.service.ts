import { Agent, AgentSession } from '../types';

export const SYSTEM_AGENTS: Agent[] = [
  {
    id: 'agent-sales-1',
    departmentId: 'dept-sales-1',
    departmentName: 'Procurement & Municipal Bids',
    name: 'Dallas Bonfire Intelligence Agent',
    code: 'AGT-BONFIRE',
    model: 'gemini-2.0-flash',
    status: 'idle',
    description: 'Autonomous Dallas City Hall procurement scraper',
    capabilities: ['Web Scraping', 'RFP Parsing', 'Bonfire Hub Navigation'],
  },
  {
    id: 'agent-sales-2',
    departmentId: 'dept-sales-2',
    departmentName: 'State Infrastructure & Construction',
    name: 'DASNY RFP & Construction Scout',
    code: 'AGT-DASNY',
    model: 'gemini-2.0-flash',
    status: 'idle',
    description: 'Autonomous New York DASNY construction RFP scraper',
    capabilities: ['Construction RFPs', 'DASNY Bid Tracker', 'Contract Analysis'],
  },
  {
    id: 'agent-email-mktg',
    departmentId: 'dept-email-mktg',
    departmentName: 'Commercial Directory Outreach',
    name: 'JWiz Commercial Directory Harvester',
    code: 'AGT-JWIZ',
    model: 'gemini-2.0-flash',
    status: 'idle',
    description: 'Autonomous JWiz commercial directory harvester',
    capabilities: ['Directory Scraping', 'Lead Extraction', 'Phone & Email Discovery'],
  },
  {
    id: 'agent-research',
    departmentId: 'dept-research',
    departmentName: 'State Contracts & Regulatory',
    name: 'NYSCR State Contract Reporter Agent',
    code: 'AGT-NYSCR',
    model: 'gemini-2.0-flash',
    status: 'idle',
    description: 'Autonomous NYSCR state contract reporter',
    capabilities: ['State Contracts', 'Notice Extraction', 'Government Bid Analysis'],
  },
  {
    id: 'agent-master',
    departmentId: 'dept-biz-dev',
    departmentName: 'Business Development & Operations',
    name: 'DataOps Master Orchestrator',
    code: 'AGT-ORCH',
    model: 'gemini-2.0-flash',
    status: 'idle',
    description: 'Central autonomous orchestration agent',
    capabilities: ['Multi-Agent Coordination', 'Pipeline Automation', 'Data Ingestion'],
  },
];

class AgentService {
  private agents: Agent[] = [...SYSTEM_AGENTS];
  private sessions: AgentSession[] = [];

  async getAgents(): Promise<Agent[]> {
    return [...this.agents];
  }

  async getAgentByDepartment(departmentId: string): Promise<Agent | undefined> {
    return this.agents.find(a => a.departmentId === departmentId) || this.agents[0];
  }

  async getSessions(departmentId?: string): Promise<AgentSession[]> {
    if (departmentId && departmentId !== 'all') {
      return this.sessions.filter(s => s.departmentId === departmentId);
    }
    return [...this.sessions];
  }

  async getSessionById(sessionId: string): Promise<AgentSession | null> {
    const found = this.sessions.find(s => s.id === sessionId);
    return found ? JSON.parse(JSON.stringify(found)) : null;
  }

  async createSession(departmentId: string, title?: string): Promise<AgentSession> {
    const agent = await this.getAgentByDepartment(departmentId);
    const newSession: AgentSession = {
      id: `sess-${Date.now()}`,
      agentId: agent?.id || 'agent-sales-1',
      departmentId,
      title: title || 'New Scraper Pipeline Request',
      createdAt: 'Just now',
      updatedAt: 'Just now',
      status: 'active',
      requirement: {
        id: `req-${Date.now()}`,
        sessionId: `sess-${Date.now()}`,
        departmentId,
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
    this.sessions.unshift(newSession);
    return newSession;
  }
}

export const agentService = new AgentService();
