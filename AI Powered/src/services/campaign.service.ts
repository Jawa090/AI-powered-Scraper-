import { Campaign } from '../types';
import { MOCK_CAMPAIGNS } from '../mock/campaigns';

class CampaignService {
  private campaigns: Campaign[] = [...MOCK_CAMPAIGNS];

  async getCampaigns(departmentId?: string): Promise<Campaign[]> {
    if (departmentId && departmentId !== 'all') {
      return this.campaigns.filter(c => c.departmentId === departmentId);
    }
    return [...this.campaigns];
  }

  async getCampaignById(id: string): Promise<Campaign | null> {
    const found = this.campaigns.find(c => c.id === id);
    return found ? { ...found } : null;
  }
}

export const campaignService = new CampaignService();
