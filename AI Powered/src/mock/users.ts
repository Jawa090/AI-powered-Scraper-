import { User } from '../types';

export const MOCK_USERS: User[] = [
  {
    id: 'usr-ahmed',
    name: 'Ahmed Khan',
    email: 'ahmed.khan@company.internal',
    role: 'sales',
    roleTitle: 'Senior Outbound Sales Specialist',
    departmentId: 'dept-sales-1',
    departmentName: 'Procurement & Bids',
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
  },
  {
    id: 'usr-sara',
    name: 'Sara Jenkins',
    email: 'sara.j@company.internal',
    role: 'email',
    roleTitle: 'Email Growth & Campaigns Lead',
    departmentId: 'dept-email-mktg',
    departmentName: 'Commercial Directory Outreach',
    avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80',
  },
  {
    id: 'usr-marcus',
    name: 'Marcus Vance',
    email: 'marcus.v@company.internal',
    role: 'manager',
    roleTitle: 'Director of State RFPs & Infrastructure',
    departmentId: 'dept-sales-2',
    departmentName: 'State Infrastructure & Construction',
    avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80',
  },
  {
    id: 'usr-elena',
    name: 'Elena Rostova',
    email: 'elena.r@company.internal',
    role: 'admin',
    roleTitle: 'Head of Enterprise Intelligence (Admin)',
    departmentId: 'dept-research',
    departmentName: 'State Contracts & Regulatory',
    avatar: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80',
  },
];
