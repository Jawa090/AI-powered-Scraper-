import { Script, Workflow, Employee } from '../types';
import { MOCK_SCRIPTS } from '../mock/scripts';
import { MOCK_WORKFLOWS } from '../mock/workflows';
import { MOCK_EMPLOYEES } from '../mock/employees';

class OpsService {
  private scripts: Script[] = [...MOCK_SCRIPTS];
  private workflows: Workflow[] = [...MOCK_WORKFLOWS];
  private employees: Employee[] = [...MOCK_EMPLOYEES];

  async getScripts(): Promise<Script[]> {
    return [...this.scripts];
  }

  async getWorkflows(): Promise<Workflow[]> {
    return [...this.workflows];
  }

  async getEmployees(departmentId?: string): Promise<Employee[]> {
    if (departmentId && departmentId !== 'all') {
      return this.employees.filter(e => e.departmentId === departmentId);
    }
    return [...this.employees];
  }

  async getEmployeeById(id: string): Promise<Employee | null> {
    const found = this.employees.find(e => e.id === id);
    return found ? { ...found } : null;
  }
}

export const opsService = new OpsService();
