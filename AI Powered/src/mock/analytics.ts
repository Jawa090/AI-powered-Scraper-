export interface FunnelStage {
  label: string;
  count: number;
  pctOfTotal: number;
  pctOfPrevious: number;
  color: string;
}

export const MOCK_FUNNEL: FunnelStage[] = [
  { label: 'Harvested / Scraped', count: 58, pctOfTotal: 100, pctOfPrevious: 100, color: '#2D4351' },
  { label: 'Assigned to Reps', count: 54, pctOfTotal: 93.1, pctOfPrevious: 93.1, color: '#3D5B6E' },
  { label: 'Contacted (Call/Email)', count: 43, pctOfTotal: 74.1, pctOfPrevious: 79.6, color: '#4E738B' },
  { label: 'Engaged & Dialog', count: 28, pctOfTotal: 48.3, pctOfPrevious: 65.1, color: '#3B82F6' },
  { label: 'Interested Pipeline', count: 20, pctOfTotal: 34.5, pctOfPrevious: 71.4, color: '#F59E0B' },
  { label: 'Qualified Opportunities', count: 12, pctOfTotal: 20.7, pctOfPrevious: 60.0, color: '#10B981' },
  { label: 'Converted / Contracts', count: 5, pctOfTotal: 8.6, pctOfPrevious: 41.7, color: '#059669' },
];

export const MOCK_ACTIVITY_CHART = {
  '7d': [
    { name: 'Mon', calls: 6, emails: 8, leads: 22 },
    { name: 'Tue', calls: 12, emails: 14, leads: 6 },
    { name: 'Wed', calls: 10, emails: 15, leads: 25 },
    { name: 'Thu', calls: 8, emails: 11, leads: 5 },
    { name: 'Fri', calls: 9, emails: 12, leads: 20 },
    { name: 'Sat', calls: 3, emails: 4, leads: 0 },
    { name: 'Sun', calls: 2, emails: 3, leads: 0 },
  ],
  '30d': [
    { name: 'Week 1', calls: 15, emails: 22, leads: 22 },
    { name: 'Week 2', calls: 24, emails: 31, leads: 31 },
    { name: 'Week 3', calls: 32, emails: 40, leads: 48 },
    { name: 'Week 4', calls: 43, emails: 52, leads: 58 },
  ],
  '90d': [
    { name: 'Month 1', calls: 40, emails: 55, leads: 45 },
    { name: 'Month 2', calls: 65, emails: 80, leads: 52 },
    { name: 'Month 3', calls: 95, emails: 120, leads: 58 },
  ],
};
