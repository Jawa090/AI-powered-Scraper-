import { Workflow } from '../types';

export const MOCK_WORKFLOWS: Workflow[] = [
  {
    id: 'wf-bonfire',
    name: 'Dallas City Hall Bonfire Procurement Workflow',
    description: 'Autonomous multi-stage pipeline extracting municipal bids, RFP notices, submission criteria, and closing dates from Dallas Bonfire Hub.',
    departmentId: 'dept-sales-1',
    status: 'Active',
    lastUsed: 'Today, 04:08 PM',
    steps: [
      { id: 'st-b1', name: 'Bonfire Portal Ingestion', type: 'Portal Scraper', status: 'completed', order: 1, description: 'Extracts open public listings and project IDs from City of Dallas Bonfire Hub' },
      { id: 'st-b2', name: 'Reference & Scope Extraction', type: 'Data Parsing', status: 'completed', order: 2, description: 'Captures solicitation title, department, reference code, and intent' },
      { id: 'st-b3', name: 'Deadline & Timeline Calculation', type: 'Date Resolver', status: 'completed', order: 3, description: 'Calculates days left, submission deadlines, and pre-bid conference schedules' },
      { id: 'st-b4', name: 'Contact & Procurement Officer Matching', type: 'Entity Resolution', status: 'completed', order: 4, description: 'Identifies city procurement contacts and procurement department' },
      { id: 'st-b5', name: 'Dataset Publishing', type: 'Schema Assembly', status: 'completed', order: 5, description: 'Publishes structured bid opportunities into DataOps Leads workspace' },
    ],
  },
  {
    id: 'wf-dasny',
    name: 'DASNY Institutional Construction RFP Harvester',
    description: 'Specialized crawler extracting architectural, engineering, and construction bid opportunities from the State of New York Dormitory Authority.',
    departmentId: 'dept-sales-2',
    status: 'Active',
    lastUsed: 'Today, 02:15 PM',
    steps: [
      { id: 'st-d1', name: 'DASNY Public Board Crawl', type: 'Web Scraper', status: 'completed', order: 1, description: 'Crawls active RFP tables and construction opportunities on dasny.org' },
      { id: 'st-d2', name: 'Solicitation Details Parsing', type: 'HTML Extraction', status: 'completed', order: 2, description: 'Parses RFP title, solicitation number, and project budget scope' },
      { id: 'st-d3', name: 'Officer & Contact Discovery', type: 'Email Regex Parser', status: 'completed', order: 3, description: 'Extracts procurement contact names, official emails, and phone numbers' },
      { id: 'st-d4', name: 'Planholders & Subcontractor Intel', type: 'Document Parsing', status: 'completed', order: 4, description: 'Identifies interested subs and mandatory walkthrough dates' },
      { id: 'st-d5', name: 'CRM Dataset Assembly', type: 'Data Store', status: 'completed', order: 5, description: 'Packages verified opportunities into State Infrastructure dataset' },
    ],
  },
  {
    id: 'wf-jwiz',
    name: 'JWiz Commercial & Services Directory Pipeline',
    description: 'High-throughput commercial contractor directory harvester extracting verified trades, direct dials, and verified emails.',
    departmentId: 'dept-email-mktg',
    status: 'Active',
    lastUsed: 'Today, 03:32 PM',
    steps: [
      { id: 'st-j1', name: 'Category & Geo Targeted Query', type: 'Directory Crawler', status: 'completed', order: 1, description: 'Performs keyword & regional queries across JWiz commercial categories' },
      { id: 'st-j2', name: 'Listing Extraction', type: 'Business Harvester', status: 'completed', order: 2, description: 'Extracts company name, business address, and website URL' },
      { id: 'st-j3', name: 'Direct Dial Phone Extraction', type: 'Phone Normalizer', status: 'completed', order: 3, description: 'Extracts and formats verified commercial contact phone numbers' },
      { id: 'st-j4', name: 'Email & Domain Enrichment', type: 'MX Validator', status: 'completed', order: 4, description: 'Captures and verifies contact email addresses' },
      { id: 'st-j5', name: 'Outreach Pipeline Export', type: 'Dataset Assembly', status: 'completed', order: 5, description: 'Directly pushes leads into Email Marketing sequence workspace' },
    ],
  },
  {
    id: 'wf-nyscr',
    name: 'NYSCR State Contract Reporter Ingestion Flow',
    description: 'Official New York State procurement portal scraper for state agency contracts, open notices, and contractor opportunities.',
    departmentId: 'dept-research',
    status: 'Active',
    lastUsed: 'Today, 01:40 PM',
    steps: [
      { id: 'st-n1', name: 'Contract Reporter Session Crawler', type: 'Session Harvester', status: 'completed', order: 1, description: 'Queries nyscr.ny.gov open public bid notices' },
      { id: 'st-n2', name: 'Agency & Solicitation Extraction', type: 'Record Parser', status: 'completed', order: 2, description: 'Captures issuing government agency, contract title, and category' },
      { id: 'st-n3', name: 'Submission Due Date Parser', type: 'Deadline Tracker', status: 'completed', order: 3, description: 'Normalizes bid submission deadlines and mandatory criteria' },
      { id: 'st-n4', name: 'Contracting Officer Parsing', type: 'Contact Extractor', status: 'completed', order: 4, description: 'Gathers agency procurement contact name and email' },
      { id: 'st-n5', name: 'State Contracts DB Publish', type: 'Final Store', status: 'completed', order: 5, description: 'Pushes verified government opportunities to repository' },
    ],
  },
];
