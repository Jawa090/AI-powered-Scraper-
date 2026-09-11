import { Script } from '../types';

export const MOCK_SCRIPTS: (Script & {
  category?: string;
  department?: string;
  file?: string;
  defaultLimit?: number;
})[] = [
  {
    id: 'bonfire',
    name: 'Dallas City Hall Bonfire Scraper',
    version: 'v1.2.0',
    status: 'Active',
    category: 'Government & Municipal Bids',
    department: 'Procurement & Bids',
    file: 'dallas_bonfire_scraper.py',
    usedBy: ['Sales 1', 'Public Sector', 'Operations'],
    capabilities: [
      'City procurement extraction',
      'Reference number parsing',
      'Closing date & days left tracker',
      'RFP / ITB scope extraction',
    ],
    description: 'Autonomous extractor for open opportunities, RFP bids, and commodity procurement from Dallas City Hall Bonfire Hub.',
    lastRun: '15 minutes ago',
    successRate: '99.2%',
    defaultLimit: 20,
  },
  {
    id: 'dasny',
    name: 'DASNY RFP & Bid Opportunities Scraper',
    version: 'v2.0.1',
    status: 'Active',
    category: 'State Authority RFPs',
    department: 'Research & Sales',
    file: 'dasny_scraper.py',
    usedBy: ['Sales 1', 'Sales 2', 'Estimating'],
    capabilities: [
      'Dormitory Authority of NY bids',
      'Public listing extraction',
      'Contact email parsing',
      'Planholders & Interested subs identification',
    ],
    description: 'Extracts construction, engineering, and architectural bid opportunities and contacts from the State of New York Dormitory Authority.',
    lastRun: '1 hour ago',
    successRate: '98.8%',
    defaultLimit: 20,
  },
  {
    id: 'jwiz',
    name: 'JWiz Commercial & Services Directory Scraper',
    version: 'v3.1.0',
    status: 'Active',
    category: 'Commercial B2B Directory',
    department: 'Sales & Email Outreach',
    file: 'jwiz.py',
    usedBy: ['Sales 1', 'Email Marketing', 'Business Development'],
    capabilities: [
      'Direct business discovery',
      'City & State geographic targeting',
      'Phone & Email validation',
      'Social / LinkedIn profiling',
    ],
    description: 'High-throughput directory extractor gathering verified commercial contractors, service providers, phone numbers, and emails.',
    lastRun: '5 minutes ago',
    successRate: '99.4%',
    defaultLimit: 25,
  },
  {
    id: 'nyscr',
    name: 'NYSCR State Contract Reporter Scraper',
    version: 'v2.4.0',
    status: 'Active',
    category: 'Statewide Contracts',
    department: 'Procurement & Enterprise',
    file: 'final_scraper.py',
    usedBy: ['Research', 'Business Development'],
    capabilities: [
      'New York State Contract Reporter extraction',
      'Agency issuing organization discovery',
      'Bid deadlines and submission criteria',
      'Verified procurement contact capture',
    ],
    description: 'Official New York State procurement portal scraper for state agency contracts, open bids, and contractor opportunities.',
    lastRun: '3 hours ago',
    successRate: '97.9%',
    defaultLimit: 25,
  },
];
