import { Job } from '../types';
import { MOCK_JOBS } from '../mock/jobs';

class JobService {
  private jobs: Job[] = [...MOCK_JOBS];

  async getJobs(departmentId?: string): Promise<Job[]> {
    if (departmentId && departmentId !== 'all') {
      return this.jobs.filter(j => j.departmentId === departmentId);
    }
    return [...this.jobs];
  }

  async getJobById(id: string): Promise<Job | null> {
    const found = this.jobs.find(j => j.id === id);
    return found ? { ...found } : null;
  }

  async createJob(job: Job): Promise<Job> {
    this.jobs = [job, ...this.jobs];
    return job;
  }

  async updateJob(id: string, updates: Partial<Job>): Promise<Job | null> {
    const idx = this.jobs.findIndex(j => j.id === id);
    if (idx !== -1) {
      this.jobs[idx] = { ...this.jobs[idx], ...updates };
      return { ...this.jobs[idx] };
    }
    return null;
  }
}

export const jobService = new JobService();
