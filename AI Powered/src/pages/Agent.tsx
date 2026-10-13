import React, { useState } from 'react';
import { useDataOps } from '../context/DataOpsContext';
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
    clearChat,
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
    if (jobId) onNavigate(`/jobs/${jobId}`);
    setIsConfirmModalOpen(false);
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
        {/* Center Column: Chat UI (Col 9) */}
        <div className="lg:col-span-9 h-full flex flex-col min-h-0">
          <AgentChat
            sessionId={activeSession.id}
            messages={currentMessages}
            onSendMessage={text => sendMessage(activeSession.id, text)}
            onClearChat={() => clearChat()}
            onExecuteAction={action => {
              if (action.actionType === 'view_results' || action.label === 'View Results') {
                onNavigate('/leads');
              } else if (action.actionType === 'view_job' || action.label === 'View Job') {
                const jId = action.parameters?.jobId || (activeSession.requirement as any).jobId;
                if (jId) {
                  onNavigate(`/jobs/${jId}`);
                } else {
                  onNavigate('/jobs');
                }
              } else if (action.parameters?.jobId) {
                onNavigate(`/jobs/${action.parameters.jobId}`);
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
                onNavigate(`/jobs/${jId}`);
              } else {
                onNavigate('/jobs');
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
