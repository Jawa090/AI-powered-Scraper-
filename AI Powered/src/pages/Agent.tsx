import React, { useState } from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { AgentSidebar } from '../components/agent/AgentSidebar';
import { AgentChat } from '../components/agent/AgentChat';
import { RequirementSummaryPanel } from '../components/agent/RequirementSummaryPanel';
import { ConfirmationModal } from '../components/agent/ConfirmationModal';

interface AgentPageProps {
  onNavigate: (path: string) => void;
}

export const Agent: React.FC<AgentPageProps> = ({ onNavigate }) => {
  const {
    sessions,
    activeSessionId,
    setActiveSessionId,
    messagesBySession,
    sendMessage,
    createSession,
    confirmRequirementAndGenerate,
  } = useDataOps();

  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);

  // Active session
  const activeSession =
    sessions.find(s => s.id === activeSessionId) || sessions[0];

  const currentMessages = (activeSession && messagesBySession[activeSession.id]) || [];

  const handleConfirmAndStart = async () => {
    if (!activeSession) return;
    const jobId = await confirmRequirementAndGenerate(activeSession.id);
    // Navigate to generation screen
    onNavigate(`/data-requests/${jobId}`);
  };

  const handleInstantTrigger = async (scriptId: string) => {
    if (!activeSession) return;
    const scriptMeta: Record<string, { name: string; industry: string; location: string; qty: number }> = {
      bonfire: {
        name: 'Dallas City Hall Bonfire Scraper',
        industry: 'Dallas Municipal Procurement Bids',
        location: 'City of Dallas, TX',
        qty: 20,
      },
      dasny: {
        name: 'DASNY RFP & Bid Opportunities Scraper',
        industry: 'DASNY NY Construction & Architectural RFPs',
        location: 'New York State',
        qty: 6,
      },
      jwiz: {
        name: 'JWiz Commercial & Services Directory Scraper',
        industry: 'Commercial Contractors & Trade Services',
        location: 'New York & Tri-State Area',
        qty: 25,
      },
      nyscr: {
        name: 'NYSCR State Contract Reporter Scraper',
        industry: 'New York State Agency Contracts',
        location: 'Albany & Statewide NY',
        qty: 5,
      },
    };

    const meta = scriptMeta[scriptId] || {
      name: scriptId,
      industry: 'Public Procurement Opportunities',
      location: 'United States',
      qty: 20,
    };

    activeSession.requirement.scriptId = scriptId;
    activeSession.requirement.scriptName = meta.name;
    activeSession.requirement.industry = meta.industry;
    activeSession.requirement.location = meta.location;
    activeSession.requirement.quantity = meta.qty;
    activeSession.requirement.completionPercentage = 100;
    activeSession.requirement.status = 'confirmed';

    const jobId = await confirmRequirementAndGenerate(activeSession.id);
    onNavigate(`/data-requests/${jobId}`);
  };

  if (!activeSession) {
    return (
      <div className="flex items-center justify-center h-96">
        <p className="text-xs text-gray-500">Loading AI Agent environment...</p>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-6.5rem)] flex flex-col">
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-0">
        {/* Left Column: Sessions (Col 3) */}
        <div className="hidden md:block lg:col-span-3 h-full">
          <AgentSidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={setActiveSessionId}
            onNewSession={() => createSession()}
          />
        </div>

        {/* Center Column: Chat UI (Col 5 / 6) */}
        <div className="lg:col-span-6 h-full flex flex-col min-h-0">
          <AgentChat
            sessionId={activeSession.id}
            messages={currentMessages}
            onSendMessage={text => sendMessage(activeSession.id, text)}
            onInstantTrigger={handleInstantTrigger}
            onResetSession={() => createSession()}
            onExecuteAction={action => {
              if (action.actionType === 'view_results' || action.label === 'View Results') {
                onNavigate('/leads');
              } else if (action.actionType === 'view_job' || action.label === 'View Job') {
                const jId = action.parameters?.jobId || (activeSession.requirement as any).jobId;
                if (jId) {
                  onNavigate(`/data-requests/${jId}`);
                } else {
                  onNavigate('/data-requests');
                }
              } else if (action.parameters?.jobId) {
                onNavigate(`/data-requests/${action.parameters.jobId}`);
              } else if (action.parameters?.script_id || action.parameters?.scriptId) {
                handleInstantTrigger(action.parameters.script_id || action.parameters.scriptId);
              } else {
                sendMessage(activeSession.id, `Execute ${action.label}`);
              }
            }}
          />
        </div>

        {/* Right Column: Requirement Summary Panel (Col 3) */}
        <div className="lg:col-span-3 h-full">
          <RequirementSummaryPanel
            requirement={activeSession.requirement}
            onConfirm={() => setIsConfirmModalOpen(true)}
            onViewJob={jobId => {
              const jId = jobId || (activeSession.requirement as any).jobId;
              if (jId) {
                onNavigate(`/data-requests/${jId}`);
              } else {
                onNavigate('/data-requests');
              }
            }}
            onViewResults={() => {
              onNavigate('/leads');
            }}
          />
        </div>
      </div>

      {/* Confirmation Modal */}
      <ConfirmationModal
        isOpen={isConfirmModalOpen}
        onClose={() => setIsConfirmModalOpen(false)}
        requirement={activeSession.requirement}
        onConfirm={handleConfirmAndStart}
      />
    </div>
  );
};
