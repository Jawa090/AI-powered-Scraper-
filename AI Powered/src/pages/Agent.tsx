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
    // Defaults only fill gaps: what the user asked for in chat (industry,
    // location, quantity) must reach the scraper unchanged. Locations here are
    // plain place names because the backend turns them into search slugs.
    const scriptMeta: Record<string, { name: string; industry: string; location: string; qty: number }> = {
      bonfire: { name: 'Dallas City Hall Bonfire Scraper', industry: 'All Open Opportunities', location: 'Dallas', qty: 20 },
      dasny: { name: 'DASNY RFP & Bid Opportunities Scraper', industry: 'All Open Opportunities', location: 'New York', qty: 20 },
      jwiz: { name: 'JWiz Commercial & Services Directory Scraper', industry: 'Contractor', location: 'New York', qty: 25 },
      nyscr: { name: 'NYSCR State Contract Reporter Scraper', industry: 'All Open Opportunities', location: 'New York', qty: 25 },
    };

    const meta = scriptMeta[scriptId] || {
      name: scriptId,
      industry: 'All Open Opportunities',
      location: 'New York',
      qty: 20,
    };

    const req = activeSession.requirement;
    const isBlank = (v?: string) => !v || v === 'Not specified';
    req.scriptId = scriptId;
    req.scriptName = meta.name;
    if (isBlank(req.industry)) req.industry = meta.industry;
    if (isBlank(req.location)) req.location = meta.location;
    if (!req.quantity || req.quantity <= 0) req.quantity = meta.qty;
    req.completionPercentage = 100;
    req.status = 'confirmed';

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
