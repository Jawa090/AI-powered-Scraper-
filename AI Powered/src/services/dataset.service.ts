import { Dataset } from '../types';
import { MOCK_DATASETS } from '../mock/datasets';

class DatasetService {
  private datasets: Dataset[] = [...MOCK_DATASETS];

  async getDatasets(departmentId?: string): Promise<Dataset[]> {
    if (departmentId && departmentId !== 'all') {
      return this.datasets.filter(d => d.departmentId === departmentId);
    }
    return [...this.datasets];
  }

  async getDatasetById(id: string): Promise<Dataset | null> {
    const found = this.datasets.find(d => d.id === id);
    return found ? { ...found } : null;
  }

  async addDataset(dataset: Dataset): Promise<Dataset> {
    this.datasets = [dataset, ...this.datasets];
    return { ...dataset };
  }

  async updateStatus(id: string, status: Dataset['status']): Promise<Dataset | null> {
    const idx = this.datasets.findIndex(d => d.id === id);
    if (idx !== -1) {
      this.datasets[idx] = { ...this.datasets[idx], status };
      return { ...this.datasets[idx] };
    }
    return null;
  }
}

export const datasetService = new DatasetService();
