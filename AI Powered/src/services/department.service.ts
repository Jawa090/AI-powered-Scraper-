import { Department } from '../types';
import { MOCK_DEPARTMENTS } from '../mock/departments';

class DepartmentService {
  private departments: Department[] = [...MOCK_DEPARTMENTS];

  async getDepartments(): Promise<Department[]> {
    return [...this.departments];
  }

  async getDepartmentById(id: string): Promise<Department | null> {
    const found = this.departments.find(d => d.id === id);
    return found ? { ...found } : null;
  }

  async incrementDepartmentStats(departmentId: string, delta: { called?: number; emailed?: number; interested?: number }): Promise<void> {
    const idx = this.departments.findIndex(d => d.id === departmentId);
    if (idx !== -1) {
      const d = this.departments[idx];
      const newCalled = d.calledCount + (delta.called || 0);
      const newEmailed = d.emailedCount + (delta.emailed || 0);
      const newInterested = d.interestedCount + (delta.interested || 0);
      const newPending = Math.max(0, d.pendingCount - (delta.called || delta.emailed || 0));
      const completionRate = Math.min(100, Math.round(((newCalled + newEmailed) / d.assignedCount) * 100));

      this.departments[idx] = {
        ...d,
        calledCount: newCalled,
        emailedCount: newEmailed,
        interestedCount: newInterested,
        pendingCount: newPending,
        completionRate,
      };
    }
  }
}

export const departmentService = new DepartmentService();
