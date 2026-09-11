import React, { useState } from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { LeadTable } from '../components/leads/LeadTable';
import { LeadDrawer } from '../components/leads/LeadDrawer';
import { CallModal } from '../components/leads/CallModal';
import { EmailComposerModal } from '../components/leads/EmailComposerModal';
import { BulkEmailModal } from '../components/leads/BulkEmailModal';
import { Lead, LeadStatus } from '../types';
import { Users2, Phone, Mail, Sparkles, Filter } from 'lucide-react';

interface LeadsProps {
  onNavigate: (path: string) => void;
}

export const Leads: React.FC<LeadsProps> = ({ onNavigate }) => {
  const { leads, kpis, logCall, sendEmail, sendBulkEmail } = useDataOps();

  // Modals & Drawer state
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const [callLead, setCallLead] = useState<Lead | null>(null);
  const [isCallModalOpen, setIsCallModalOpen] = useState(false);

  const [emailLead, setEmailLead] = useState<Lead | null>(null);
  const [isEmailModalOpen, setIsEmailModalOpen] = useState(false);

  const [bulkLeads, setBulkLeads] = useState<Lead[]>([]);
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);

  const handleRowClick = (lead: Lead) => {
    setSelectedLead(lead);
    setIsDrawerOpen(true);
  };

  const handleOpenCall = (lead: Lead) => {
    setCallLead(lead);
    setIsCallModalOpen(true);
  };

  const handleOpenEmail = (lead: Lead) => {
    setEmailLead(lead);
    setIsEmailModalOpen(true);
  };

  const handleOpenBulkEmail = (selected: Lead[]) => {
    setBulkLeads(selected);
    setIsBulkModalOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-gray-900">Leads Workspace</h1>
            <span className="text-xs font-mono font-semibold bg-[#2D4351] text-white px-2 py-0.5 rounded-full">
              {kpis.totalLeads.toLocaleString()} total
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-0.5">
            Autonomous verified contact registry with direct telephone dialing and mailbox sequence tools
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('/agent')}
            className="px-3.5 py-2 rounded-lg bg-[#2D4351] text-white hover:bg-[#20313C] text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span>Generate New Leads</span>
          </button>
        </div>
      </div>

      {/* Main Enterprise Lead Table */}
      <LeadTable
        leads={leads}
        onSelectLead={handleRowClick}
        onCallLead={handleOpenCall}
        onEmailLead={handleOpenEmail}
        onOpenBulkEmail={handleOpenBulkEmail}
      />

      {/* Slide-over Detail Drawer */}
      <LeadDrawer
        lead={selectedLead}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        onCall={lead => {
          setIsDrawerOpen(false);
          handleOpenCall(lead);
        }}
        onEmail={lead => {
          setIsDrawerOpen(false);
          handleOpenEmail(lead);
        }}
      />

      {/* Call Modal */}
      <CallModal
        lead={callLead}
        isOpen={isCallModalOpen}
        onClose={() => setIsCallModalOpen(false)}
        onSaveCall={(id, outcome, notes, nextFollowUp) => {
          logCall(id, outcome, notes, nextFollowUp);
        }}
      />

      {/* Single Email Composer Modal */}
      <EmailComposerModal
        lead={emailLead}
        isOpen={isEmailModalOpen}
        onClose={() => setIsEmailModalOpen(false)}
        onSendEmail={(id, subject, body) => {
          sendEmail(id, subject, body);
        }}
      />

      {/* Bulk Email Outreach Modal */}
      <BulkEmailModal
        selectedLeads={bulkLeads}
        isOpen={isBulkModalOpen}
        onClose={() => setIsBulkModalOpen(false)}
        onSendBulk={async (ids, subject, body) => {
          await sendBulkEmail(ids, subject, body);
        }}
      />
    </div>
  );
};
