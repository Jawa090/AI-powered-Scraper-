import { Lead, LeadStatus } from '../types';
import { MOCK_LEADS } from '../mock/leads';

class LeadService {
  private leads: Lead[] = [...MOCK_LEADS];

  async getLeads(filters?: {
    departmentId?: string;
    status?: string;
    query?: string;
    datasetId?: string;
  }): Promise<Lead[]> {
    let result = [...this.leads];

    if (filters?.departmentId && filters.departmentId !== 'all') {
      result = result.filter(l => l.departmentId === filters.departmentId);
    }
    if (filters?.status && filters.status !== 'all') {
      result = result.filter(l => l.status === filters.status);
    }
    if (filters?.datasetId) {
      result = result.filter(l => l.datasetId === filters.datasetId);
    }
    if (filters?.query) {
      const q = filters.query.toLowerCase();
      result = result.filter(
        l =>
          l.name.toLowerCase().includes(q) ||
          l.company.toLowerCase().includes(q) ||
          l.title.toLowerCase().includes(q) ||
          l.email.toLowerCase().includes(q) ||
          l.location.toLowerCase().includes(q)
      );
    }

    return result;
  }

  async getLeadById(id: string): Promise<Lead | null> {
    const lead = this.leads.find(l => l.id === id);
    return lead ? { ...lead } : null;
  }

  async updateLeadStatus(id: string, status: LeadStatus, notes?: string, nextFollowUp?: string): Promise<Lead> {
    const idx = this.leads.findIndex(l => l.id === id);
    if (idx !== -1) {
      this.leads[idx] = {
        ...this.leads[idx],
        status,
        notes: notes !== undefined ? notes : this.leads[idx].notes,
        nextFollowUp: nextFollowUp !== undefined ? nextFollowUp : this.leads[idx].nextFollowUp,
        lastActivity: 'Just now',
      };
      return { ...this.leads[idx] };
    }
    throw new Error(`Lead ${id} not found`);
  }

  async updateBulkStatus(ids: string[], status: LeadStatus): Promise<Lead[]> {
    const updated: Lead[] = [];
    this.leads = this.leads.map(l => {
      if (ids.includes(l.id)) {
        const item: Lead = {
          ...l,
          status,
          lastActivity: 'Just now (Bulk Action)',
        };
        updated.push(item);
        return item;
      }
      return l;
    });
    return updated;
  }

  async addLeads(newLeads: Lead[]): Promise<Lead[]> {
    this.leads = [...newLeads, ...this.leads];
    return this.leads;
  }
}

export const leadService = new LeadService();
