import { Activity } from '../types';

export const MOCK_ACTIVITIES: Activity[] = [
  {
    "id": "act-bonfire-1",
    "type": "generation",
    "title": "Dallas City Hall Procurement Harvest",
    "description": "Autonomous Bonfire scraper extracted 22 open municipal procurement opportunities from City of Dallas.",
    "user": "Ahmed Khan",
    "department": "Public Sector Sales",
    "timestamp": "15m ago",
    "datasetId": "ds-dallas-bonfire",
    "badgeColor": "#10B981"
  },
  {
    "id": "act-jwiz-1",
    "type": "generation",
    "title": "JWiz Commercial Directory Harvest",
    "description": "Extracted verified commercial plumbing and contractor leads with phone numbers and emails.",
    "user": "Ahmed Khan",
    "department": "Sales 1",
    "timestamp": "45m ago",
    "datasetId": "ds-df0b49",
    "badgeColor": "#3B82F6"
  },
  {
    "id": "act-dasny-1",
    "type": "generation",
    "title": "DASNY Institutional Bids Crawl",
    "description": "Captured active architectural and mechanical RFPs from State of New York Dormitory Authority.",
    "user": "Ahmed Khan",
    "department": "State Contracts & RFPs",
    "timestamp": "2h ago",
    "datasetId": "ds-dasny-rfps",
    "badgeColor": "#8B5CF6"
  },
  {
    "id": "act-nyscr-1",
    "type": "generation",
    "title": "NYSCR State Contract Reporter Sync",
    "description": "State agency open contracts crawled with issuing organizations and submission criteria.",
    "user": "Ahmed Khan",
    "department": "Public Sector Procurement",
    "timestamp": "3h ago",
    "datasetId": "ds-nyscr-contracts",
    "badgeColor": "#F59E0B"
  }
];
