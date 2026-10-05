import React, { useState, useRef, useEffect } from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { AgentMessage, ProposedAction } from '../../types';
import { MultiAgentWorkflowVisualizer } from './MultiAgentWorkflowVisualizer';
import { LeadTable } from '../leads/LeadTable';
import {
  Send,
  Bot,
  Sparkles,
  RotateCcw,
  Zap,
  CheckCircle,
  Database,
  Search,
  Mail,
  TrendingUp,
  AlertCircle,
  Target,
} from 'lucide-react';

interface AgentChatProps {
  sessionId: string;
  messages: AgentMessage[];
  onSendMessage: (text: string) => void;
  onInstantTrigger?: (scriptId: string) => void;
  onResetSession?: () => void;
  onExecuteAction?: (action: ProposedAction) => void;
}

const AGENT_BADGE_STYLES: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; bg: string; text: string }> = {
  data: { label: 'Data Agent', icon: Database, bg: 'bg-blue-50 border-blue-200', text: 'text-blue-700' },
  database: { label: 'Database Agent', icon: Database, bg: 'bg-blue-50 border-blue-200', text: 'text-blue-700' },
  research: { label: 'Research Agent', icon: Search, bg: 'bg-purple-50 border-purple-200', text: 'text-purple-700' },
  sales: { label: 'Sales Agent', icon: Target, bg: 'bg-amber-50 border-amber-200', text: 'text-amber-700' },
  email: { label: 'Email Agent', icon: Mail, bg: 'bg-rose-50 border-rose-200', text: 'text-rose-700' },
  growth: { label: 'Growth Agent', icon: TrendingUp, bg: 'bg-emerald-50 border-emerald-200', text: 'text-emerald-700' },
  scraper: { label: 'Scraper Engine', icon: Bot, bg: 'bg-cyan-50 border-cyan-200', text: 'text-cyan-700' },
  orchestrator: { label: 'AI Orchestrator', icon: Bot, bg: 'bg-indigo-50 border-indigo-200', text: 'text-indigo-700' },
};

export const AgentChat: React.FC<AgentChatProps> = ({
  sessionId,
  messages,
  onSendMessage,
  onInstantTrigger,
  onResetSession,
  onExecuteAction,
}) => {
  const { currentUser, confirmBotDecision, retryBotMessage } = useDataOps();
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSend = (textToSend?: string) => {
    const text = textToSend || inputText;
    if (!text.trim()) return;

    onSendMessage(text);
    setInputText('');
    setIsTyping(true);

    setTimeout(() => {
      setIsTyping(false);
    }, 600);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl flex flex-col h-full overflow-hidden shadow-card">
      {/* Chat Header */}
      <div className="p-3.5 border-b border-[#E5E7EB] flex items-center justify-between bg-white">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#2D4351] text-white flex items-center justify-center shadow-sm">
            <Bot className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-gray-900">
                {currentUser.departmentName || 'Enterprise'} AI Agent
              </span>
              <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 font-semibold">
                Online
              </span>
            </div>
            <p className="text-[11px] text-[#848485]">
              Autonomous 4-engine scraper & LangGraph intelligence agent
            </p>
          </div>
        </div>

        {/* Header Actions & KB status */}
        <div className="flex items-center gap-2">
          {/* KB Status Chip */}
          <span className="text-[11px] font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200 flex items-center gap-1">
            <Database className="w-3 h-3 text-purple-600" />
            <span>KB Ready</span>
          </span>

          {onResetSession && (
            <button
              onClick={onResetSession}
              title="Reset Conversation Session"
              className="text-[11px] text-gray-600 hover:text-gray-900 px-2 py-1 rounded hover:bg-gray-100 transition-colors flex items-center gap-1 border border-gray-200"
            >
              <RotateCcw className="w-3 h-3" />
              <span>New Session</span>
            </button>
          )}
          <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-emerald-600" />
            Active
          </span>
        </div>
      </div>

      {/* 4 Scraper Engines Toolbar */}
      <div className="bg-[#F8F9FA] border-b border-[#E5E7EB] px-3.5 py-2 flex items-center justify-between gap-2 overflow-x-auto">
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 whitespace-nowrap flex items-center gap-1">
          <Zap className="w-3 h-3 text-indigo-500" />
          Quick Engines:
        </span>
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          {[
            { id: 'bonfire', icon: '🏛️', name: 'Dallas Bonfire', fullName: 'Dallas City Hall Bonfire Scraper' },
            { id: 'dasny', icon: '🏢', name: 'DASNY RFPs', fullName: 'DASNY RFP & Bid Opportunities Scraper' },
            { id: 'jwiz', icon: '📒', name: 'JWiz Directory', fullName: 'JWiz Commercial & Services Directory Scraper' },
            { id: 'nyscr', icon: '📜', name: 'NYSCR Contracts', fullName: 'NYSCR State Contract Reporter Scraper' },
          ].map(sc => (
            <div key={sc.id} className="inline-flex items-center rounded-lg border border-gray-200 bg-white shadow-subtle overflow-hidden">
              <button
                type="button"
                onClick={() => (onInstantTrigger ? onInstantTrigger(sc.id) : handleSend(sc.fullName))}
                title={`Trigger ${sc.name} scraper engine`}
                className="text-[11px] font-semibold px-2.5 py-1 hover:bg-emerald-50 hover:text-emerald-800 text-gray-800 transition-colors flex items-center gap-1 border-r border-gray-100 cursor-pointer"
              >
                <span>{sc.icon}</span>
                <span>{sc.name}</span>
                <span className="text-[9px] bg-emerald-100 text-emerald-800 px-1 py-0.2 rounded font-mono font-bold ml-1">⚡ Run</span>
              </button>
              <button
                type="button"
                onClick={() => handleSend(`Find records using ${sc.fullName}.`)}
                title={`Chat about ${sc.name}`}
                className="text-[10px] font-medium px-2 py-1 text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors cursor-pointer"
              >
                💬 Ask
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#F8F9FA]/40">
        {messages.map(msg => {
          const isUser = msg.sender === 'user';
          const agentBadge = msg.agentCode ? AGENT_BADGE_STYLES[msg.agentCode.toLowerCase()] : null;
          const BadgeIcon = agentBadge ? agentBadge.icon : Bot;

          return (
            <div
              key={msg.id}
              className={`flex gap-3 max-w-[92%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`}
            >
              {/* Avatar */}
              {isUser ? (
                <div className="w-7 h-7 rounded-full bg-[#2D4351] text-white flex items-center justify-center flex-shrink-0 text-xs font-semibold ring-1 ring-gray-200">
                  {currentUser.name ? currentUser.name.charAt(0).toUpperCase() : 'U'}
                </div>
              ) : (
                <div className="w-7 h-7 rounded-full bg-[#2D4351] text-white flex items-center justify-center flex-shrink-0 text-xs shadow-sm">
                  <Bot className="w-3.5 h-3.5 text-emerald-300" />
                </div>
              )}

              {/* Message Bubble Container */}
              <div className="space-y-2 flex-1 min-w-0">
                {/* Attribution and Badges */}
                {!isUser && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {agentBadge && (
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold border ${agentBadge.bg} ${agentBadge.text}`}
                      >
                        <BadgeIcon className="w-3 h-3" />
                        {agentBadge.label}
                      </span>
                    )}

                    {/* KB Status Chip on message */}
                    {msg.kb && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-purple-50 border border-purple-200 text-purple-700">
                        <Database className="w-3 h-3 text-purple-600" />
                        <span>KB: {msg.kb.available ? 'Ready' : (msg.kb.state || 'Active')}</span>
                        {msg.kb.hits && msg.kb.hits.length > 0 && (
                          <span className="bg-purple-200/60 px-1 rounded text-[9px] font-mono">
                            {msg.kb.hits.length} hit{msg.kb.hits.length > 1 ? 's' : ''}
                          </span>
                        )}
                      </span>
                    )}

                    {msg.decision && (
                      <span className="text-[9px] font-mono uppercase bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded border border-gray-200">
                        {msg.decision}
                      </span>
                    )}
                  </div>
                )}

                {/* 503 Error State */}
                {msg.is503 ? (
                  <div className="bg-rose-50 border border-rose-200 rounded-xl p-3.5 text-xs text-rose-800 space-y-2 shadow-subtle">
                    <div className="flex items-center gap-2 font-semibold">
                      <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                      <span>The AI API is not responding</span>
                    </div>
                    <p className="text-[11px] text-rose-700">
                      The AI API is not responding. Please try again.
                    </p>
                    <button
                      type="button"
                      onClick={() => retryBotMessage?.(sessionId, msg.failedClientMessageId || msg.id, msg.failedText || '')}
                      className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm cursor-pointer mt-1"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Retry</span>
                    </button>
                  </div>
                ) : (
                  /* Standard Bubble Text */
                  <div
                    className={`rounded-xl px-4 py-2.5 text-xs leading-relaxed ${
                      isUser
                        ? 'bg-[#2D4351] text-white rounded-tr-none shadow-sm'
                        : 'bg-white border border-[#E5E7EB] text-gray-900 rounded-tl-none shadow-subtle'
                    }`}
                  >
                    <div className="whitespace-pre-wrap">
                      {msg.text
                        ? msg.text
                            .replace(/\*\*([^*]+)\*\*/g, '$1')
                            .replace(/^#+\s*/gm, '')
                            .replace(/`([^`]+)`/g, '$1')
                        : ''}
                    </div>
                  </div>
                )}

                {/* LeadTable Rendering for Discovered Records */}
                {!isUser && msg.records && msg.records.length > 0 && (
                  <div className="mt-2.5 bg-white rounded-xl border border-gray-200 overflow-hidden shadow-subtle">
                    <div className="px-3.5 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                      <span className="text-xs font-bold text-gray-800 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                        Extracted Lead Records ({msg.records.length})
                      </span>
                      {msg.total !== undefined && msg.total > msg.records.length && (
                        <span className="text-[10px] text-gray-500 font-mono">Total available: {msg.total}</span>
                      )}
                    </div>
                    <div className="max-h-72 overflow-y-auto">
                      <LeadTable leads={msg.records} compact={true} />
                    </div>
                  </div>
                )}

                {/* Pending Action: Approve / Reject Buttons */}
                {!isUser && msg.pendingAction && (
                  <div className="mt-2.5 p-3 rounded-xl bg-amber-50/80 border border-amber-200 text-xs space-y-2">
                    <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                      <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                      <span>Confirmation Required</span>
                    </div>
                    <p className="text-amber-800 text-[11px]">
                      {typeof msg.pendingAction === 'string'
                        ? msg.pendingAction
                        : msg.pendingAction?.label || 'The agent proposed running a targeted scrape. Would you like to proceed?'}
                    </p>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => confirmBotDecision?.(sessionId, 'approve')}
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs transition-colors flex items-center gap-1 shadow-sm cursor-pointer"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>Approve</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => confirmBotDecision?.(sessionId, 'reject')}
                        className="px-3 py-1.5 rounded-lg bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 font-semibold text-xs transition-colors cursor-pointer"
                      >
                        <span>Reject</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Layer 12 Multi-Agent Collaboration DAG Visualizer */}
                {!isUser && (msg.collaborationId || (msg.agentSteps && msg.agentSteps.length > 1)) && (
                  <MultiAgentWorkflowVisualizer
                    collaborationId={msg.collaborationId}
                    collaborationStatus={msg.collaborationStatus}
                    agentsInvolved={msg.agentsInvolved}
                    agentSteps={msg.agentSteps}
                  />
                )}

                {/* Proposed Actions Cards */}
                {!isUser && msg.proposedActions && msg.proposedActions.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
                      Proposed Next Actions:
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {msg.proposedActions.map((action, aIdx) => (
                        <div
                          key={aIdx}
                          className="flex items-center justify-between p-2 rounded-lg bg-white border border-indigo-200 shadow-sm text-xs"
                        >
                          <div className="min-w-0 pr-2">
                            <span className="font-semibold text-gray-900 block truncate">{action.label}</span>
                            <span className="text-[10px] text-gray-400 font-mono">{action.actionType}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => (onExecuteAction ? onExecuteAction(action) : handleSend(`Execute ${action.label}`))}
                            className="px-2.5 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 text-[11px] font-medium flex items-center gap-1 transition-colors flex-shrink-0"
                          >
                            <CheckCircle className="w-3 h-3" />
                            <span>Action</span>
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Quick Action Suggestion Chips */}
                {msg.suggestions && msg.suggestions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {msg.suggestions.map(s => (
                      <button
                        key={s}
                        onClick={() => handleSend(s)}
                        className="text-[11px] px-2.5 py-1 rounded-full bg-white border border-gray-200 text-gray-700 hover:border-[#2D4351] hover:text-[#2D4351] hover:bg-gray-50 transition-all shadow-subtle cursor-pointer"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}

                <p
                  className={`text-[10px] text-gray-400 ${
                    isUser ? 'text-right' : 'text-left'
                  }`}
                >
                  {msg.timestamp}
                </p>
              </div>
            </div>
          );
        })}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex gap-3 max-w-[85%]">
            <div className="w-7 h-7 rounded-full bg-[#2D4351] text-white flex items-center justify-center flex-shrink-0">
              <Bot className="w-3.5 h-3.5 text-emerald-300" />
            </div>
            <div className="bg-white border border-[#E5E7EB] rounded-xl rounded-tl-none px-4 py-2.5 shadow-subtle">
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" />
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0.2s]" />
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0.4s]" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="p-3 border-t border-[#E5E7EB] bg-white">
        <div className="relative flex items-center">
          <input
            type="text"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your data requirement or ask our multi-agent intelligence..."
            className="w-full bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg pl-3 pr-12 py-2.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351] focus:border-[#2D4351]"
          />
          <div className="absolute right-1.5 flex items-center gap-1">
            <button
              type="button"
              onClick={() => handleSend()}
              disabled={!inputText.trim()}
              className={`p-1.5 rounded-md transition-colors ${
                inputText.trim()
                  ? 'bg-[#2D4351] text-white hover:bg-[#20313C]'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
