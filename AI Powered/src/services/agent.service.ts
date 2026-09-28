import { Agent, AgentSession, AgentMessage, Requirement } from '../types';
import { MOCK_AGENTS } from '../mock/agents';

class AgentService {
  private agents: Agent[] = [...MOCK_AGENTS];
  private sessions: AgentSession[] = [
    {
      id: 'sess-bonfire',
      agentId: 'agent-sales-1',
      departmentId: 'dept-sales-1',
      title: 'Dallas City Hall Bonfire Scraper',
      createdAt: 'Today, 04:08 PM',
      updatedAt: '04:10 PM',
      status: 'active',
      requirement: {
        id: 'req-bonfire',
        sessionId: 'sess-bonfire',
        departmentId: 'dept-sales-1',
        industry: 'Municipal Procurement & Public Works',
        location: 'City of Dallas, Texas',
        companySize: 'Government Solicitations',
        decisionMakers: ['Dallas City Procurement Officers', 'Buyers'],
        quantity: 20,
        requiredFields: {
          companyName: true,
          contactName: true,
          jobTitle: true,
          email: true,
          phone: true,
          website: true,
        },
        completionPercentage: 100,
        status: 'completed',
        datasetId: 'ds-dallas-bonfire',
        scriptId: 'bonfire',
        scriptName: 'Dallas City Hall Bonfire Scraper',
      },
    },
    {
      id: 'sess-jwiz',
      agentId: 'agent-email-mktg',
      departmentId: 'dept-email-mktg',
      title: 'JWiz Commercial Contractors Directory',
      createdAt: 'Today, 03:32 PM',
      updatedAt: '03:35 PM',
      status: 'completed',
      requirement: {
        id: 'req-jwiz',
        sessionId: 'sess-jwiz',
        departmentId: 'dept-email-mktg',
        industry: 'Commercial Contractors & Trade Services',
        location: 'New York & Tri-State Area',
        companySize: 'Commercial Plumbers, Electricians, HVAC',
        decisionMakers: ['Owners', 'Principal Contractors'],
        quantity: 25,
        requiredFields: {
          companyName: true,
          contactName: true,
          jobTitle: true,
          email: true,
          phone: true,
          website: true,
        },
        completionPercentage: 100,
        status: 'completed',
        datasetId: 'ds-df0b49',
        scriptId: 'jwiz',
        scriptName: 'JWiz Commercial & Services Directory Scraper',
      },
    },
    {
      id: 'sess-dasny',
      agentId: 'agent-sales-2',
      departmentId: 'dept-sales-2',
      title: 'DASNY NY Construction & Architectural RFPs',
      createdAt: 'Today, 02:15 PM',
      updatedAt: '02:18 PM',
      status: 'completed',
      requirement: {
        id: 'req-dasny',
        sessionId: 'sess-dasny',
        departmentId: 'dept-sales-2',
        industry: 'State Infrastructure & Architectural Solicitations',
        location: 'New York State',
        companySize: 'Public Authority Bids',
        decisionMakers: ['DASNY Contracting Officers', 'Procurement Leads'],
        quantity: 6,
        requiredFields: {
          companyName: true,
          contactName: true,
          jobTitle: true,
          email: true,
          phone: true,
          website: true,
        },
        completionPercentage: 100,
        status: 'completed',
        datasetId: 'ds-dasny-rfps',
        scriptId: 'dasny',
        scriptName: 'DASNY RFP & Bid Opportunities Scraper',
      },
    },
    {
      id: 'sess-nyscr',
      agentId: 'agent-research',
      departmentId: 'dept-research',
      title: 'NYSCR State Contract Reporter Ingestion',
      createdAt: 'Today, 01:40 PM',
      updatedAt: '01:45 PM',
      status: 'completed',
      requirement: {
        id: 'req-nyscr',
        sessionId: 'sess-nyscr',
        departmentId: 'dept-research',
        industry: 'Official State Agency Procurement Contracts',
        location: 'Albany & Statewide NY',
        companySize: 'Government Solicitations',
        decisionMakers: ['State Agency Buyers', 'Procurement Directors'],
        quantity: 5,
        requiredFields: {
          companyName: true,
          contactName: true,
          jobTitle: true,
          email: true,
          phone: true,
          website: true,
        },
        completionPercentage: 100,
        status: 'completed',
        datasetId: 'ds-nyscr-contracts',
        scriptId: 'nyscr',
        scriptName: 'NYSCR State Contract Reporter Scraper',
      },
    },
  ];

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
