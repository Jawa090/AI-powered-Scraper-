import { Activity } from '../types';
import { MOCK_ACTIVITIES } from '../mock/activities';

class ActivityService {
  private activities: Activity[] = [...MOCK_ACTIVITIES];

  async getActivities(): Promise<Activity[]> {
    return [...this.activities];
  }

  async addActivity(act: Omit<Activity, 'id' | 'timestamp'>): Promise<Activity> {
    const newAct: Activity = {
      ...act,
      id: `act-${Date.now()}`,
      timestamp: 'Just now',
    };
    this.activities = [newAct, ...this.activities];
    return newAct;
  }
}

export const activityService = new ActivityService();
