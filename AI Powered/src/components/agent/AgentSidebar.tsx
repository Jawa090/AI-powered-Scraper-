import React from 'react';
import { AgentSession } from '../../types';
import { Plus, MessageSquare, Clock, CheckCircle, Sparkles } from 'lucide-react';

interface AgentSidebarProps {
  sessions: AgentSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
}

export const AgentSidebar: React.FC<AgentSidebarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
}) => {
  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl flex flex-col h-full overflow-hidden shadow-card">
      <div className="p-3.5 border-b border-[#E5E7EB] flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-gray-900">Agent Sessions</h3>
          <p className="text-[11px] text-[#848485]">Previous intelligence requests</p>
        </div>
        <button
          onClick={onNewSession}
          className="p-1.5 rounded-lg bg-[#2D4351] text-white hover:bg-[#20313C] transition-colors"
          title="New Request"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-[#848485]">
          Active Requests
        </p>
        {sessions.map(session => {
          const isActive = session.id === activeSessionId;
          return (
            <button
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={`w-full text-left p-2.5 rounded-lg transition-all flex flex-col gap-1 ${
                isActive
                  ? 'bg-[#EAEFF2] border border-[#2D4351]/30 shadow-subtle'
                  : 'hover:bg-gray-50 border border-transparent'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-900 truncate">
                  {session.title}
                </span>
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    session.status === 'completed'
                      ? 'bg-emerald-500'
                      : session.status === 'generating'
                      ? 'bg-sky-500 animate-pulse'
                      : 'bg-amber-500'
                  }`}
                />
              </div>
              <div className="flex items-center justify-between text-[11px] text-[#848485]">
                <span>{session.createdAt}</span>
                <span className="font-medium text-gray-600">
                  {session.requirement.completionPercentage}%
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
