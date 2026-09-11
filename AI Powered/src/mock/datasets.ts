import { Dataset } from '../types';

export const MOCK_DATASETS: Dataset[] = [
  {
    "id": "ds-9db6a2",
    "name": "Dallas City Hall Bonfire Scraper (Sep 11, 16:08)",
    "departmentId": "dept-sales-1",
    "departmentName": "Procurement & Bids",
    "createdBy": "usr-ahmed",
    "createdByName": "Ahmed Khan",
    "recordsCount": 20,
    "verifiedCount": 18,
    "duplicatesCount": 1,
    "status": "Completed",
    "createdAt": "2026-09-11 04:08 PM",
    "tags": [
      "BONFIRE",
      "Live Scraped",
      "Automated"
    ],
    "workflowId": "wf-bonfire",
    "workflowName": "Dallas City Hall Bonfire Scraper Autonomous Pipeline"
  },
  {
    "id": "ds-dallas-bonfire",
    "name": "City of Dallas Procurement Opportunities (Bonfire Hub)",
    "departmentId": "dept-sales-1",
    "departmentName": "Public Sector Sales",
    "createdBy": "usr-ahmed",
    "createdByName": "Ahmed Khan",
    "recordsCount": 22,
    "verifiedCount": 22,
    "duplicatesCount": 0,
    "status": "Completed",
    "createdAt": "Today, 03:31 PM",
    "tags": [
      "BONFIRE",
      "City of Dallas",
      "Municipal Bids",
      "Live Scraped"
    ],
    "workflowId": "wf-bonfire",
    "workflowName": "Dallas Bonfire Autonomous Extractor"
  },
  {
    "id": "ds-df0b49",
    "name": "JWiz Commercial & Services Directory Scraper (Sep 11, 15:32)",
    "departmentId": "dept-sales-1",
    "departmentName": "Sales & Email Outreach",
    "createdBy": "usr-ahmed",
    "createdByName": "Ahmed Khan",
    "recordsCount": 5,
    "verifiedCount": 3,
    "duplicatesCount": 1,
    "status": "Completed",
    "createdAt": "2026-09-11 03:32 PM",
    "tags": [
      "JWIZ",
      "Live Scraped",
      "Automated"
    ],
    "workflowId": "wf-jwiz",
    "workflowName": "JWiz Commercial & Services Directory Scraper Autonomous Pipeline"
  },
  {
    "id": "ds-dasny-rfps",
    "name": "DASNY Institutional Construction RFPs & Bids",
    "departmentId": "dept-sales-1",
    "departmentName": "State Contracts & RFPs",
    "createdBy": "usr-ahmed",
    "createdByName": "Ahmed Khan",
    "recordsCount": 6,
    "verifiedCount": 6,
    "duplicatesCount": 0,
    "status": "Completed",
    "createdAt": "Today, 02:15 PM",
    "tags": [
      "DASNY",
      "New York",
      "RFP Bids",
      "Live Scraped"
    ],
    "workflowId": "wf-dasny",
    "workflowName": "DASNY Automated Opportunities Crawler"
  },
  {
    "id": "ds-nyscr-contracts",
    "name": "New York State Contract Reporter (NYSCR Open Ads)",
    "departmentId": "dept-sales-1",
    "departmentName": "Public Sector Procurement",
    "createdBy": "usr-ahmed",
    "createdByName": "Ahmed Khan",
    "recordsCount": 5,
    "verifiedCount": 5,
    "duplicatesCount": 0,
    "status": "Completed",
    "createdAt": "Today, 01:40 PM",
    "tags": [
      "NYSCR",
      "State Contracts",
      "Open Opportunities",
      "Live Scraped"
    ],
    "workflowId": "wf-nyscr",
    "workflowName": "NYSCR Autonomous Contract Harvester"
  }
];
