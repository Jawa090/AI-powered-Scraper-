import React, { useState, useRef, useEffect } from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { AgentMessage, ProposedAction, Lead } from '../../types';
import { MultiAgentWorkflowVisualizer } from './MultiAgentWorkflowVisualizer';
import { LeadTable } from '../leads/LeadTable';
import { LeadDrawer } from '../leads/LeadDrawer';
import {
  Send,
  Bot,
  Sparkles,
  RotateCcw,
  X,
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
  onClearChat?: () => void;
  onExecuteAction?: (action: ProposedAction) => void;
}

const AGENT_BADGE_STYLES: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; bg: string; text: string }> = {
  data: { label: 'Data Agent', icon: Database, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  database: { label: 'Database Agent', icon: Database, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  research: { label: 'Research Agent', icon: Search, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  sales: { label: 'Sales Agent', icon: Target, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  email: { label: 'Email Agent', icon: Mail, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  growth: { label: 'Growth Agent', icon: TrendingUp, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  scraper: { label: 'Scraper Engine', icon: Bot, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
  orchestrator: { label: 'AI Orchestrator', icon: Bot, bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800', text: 'text-blue-600 dark:text-blue-500' },
};

export const AgentChat: React.FC<AgentChatProps> = ({
  sessionId,
  messages,
  onSendMessage,
  onClearChat,
  onExecuteAction,
}) => {
  const { currentUser, confirmBotDecision, retryBotMessage, newOnly, setNewOnly } = useDataOps();
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  useEffect(() => { setSelectedLead(null); }, [sessionId]);
  useEffect(() => { setIsTyping(false); }, [sessionId]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSend = async (textToSend?: string) => {
    const text = textToSend || inputText;
    if (!text.trim()) return;

    if (isTyping) return;
    setInputText(''); setIsTyping(true);
    try { await onSendMessage(text); } finally { setIsTyping(false); }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleScrapeDecision = async (decision: 'approve' | 'reject', proposalId?: string) => {
    if (isTyping) return;
    setIsTyping(true);
    try {
      await confirmBotDecision(sessionId, decision, proposalId);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="bg-white dark:bg-black border border-[#E5E7EB] dark:border-gray-800 rounded-xl flex flex-col h-full overflow-hidden shadow-card transition-colors">
      {/* Chat Header */}
      <div className="p-3.5 border-b border-[#E5E7EB] dark:border-gray-800 flex items-center justify-between bg-white dark:bg-black">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#2D4351] text-white flex items-center justify-center shadow-sm overflow-hidden">
            <img src="/logo.jpg" alt="Agent Logo" className="w-full h-full object-cover" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-gray-900 dark:text-golden-500">
                Constructor Agent
              </span>
              <span className="text-[10px] bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 px-1.5 py-0.5 rounded border font-semibold">
                Online
              </span>
            </div>
            <p className="text-[11px] text-[#848485]">
              By Bitwords.inc
            </p>
          </div>
        </div>

        {/* Header Actions & KB status */}
        <div className="flex items-center gap-2">
          {/* KB Status Chip */}
          {/*
          
          <span className="text-[11px] font-semibold bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 px-2 py-0.5 rounded border flex items-center gap-1">
            <Database className="w-3 h-3 text-blue-600 dark:text-blue-500" />
            <span>KB Ready</span>
          </span>
          */}

          {onClearChat && (
            <label className="text-xs text-gray-700 dark:text-gray-200 flex items-center gap-2">
              <input type="checkbox" checked={newOnly} onChange={event => setNewOnly(event.target.checked)} />
              New data only
            </label>
          )}
          {onClearChat && (
            <button
              onClick={onClearChat}
              title="Clear Chat"
              className="text-[11px] text-gray-600 hover:text-red-600 px-2 py-1 rounded hover:bg-red-50 dark:hover:bg-red-900/30 dark:hover:text-red-500 transition-colors flex items-center gap-1 border border-gray-200"
            >
              <X className="w-3 h-3" />
              <span>Clear Chat</span>
            </button>
          )}
          {/*
          <span className="text-[11px] font-semibold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 px-2 py-0.5 rounded border flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-green-600 dark:text-green-500" />
            Active
          </span>
          */}
        </div>
      </div>


      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#F8F9FA]/40 dark:bg-gray-900/40">
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
                  <Bot className="w-3.5 h-3.5 text-green-300" />
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
                    {/*
                    {msg.kb && msg.decision !== 'NONE' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 border">
                        <Database className="w-3 h-3 text-blue-600 dark:text-blue-500" />
                        <span>KB: {msg.kb.available ? 'Ready' : (msg.kb.state || 'Active')}</span>
                        {msg.kb.hits && msg.kb.hits.length > 0 && (
                          <span className="bg-blue-200/60 dark:bg-blue-900/60 px-1 rounded text-[9px] font-mono">
                            {msg.kb.hits.length} hit{msg.kb.hits.length > 1 ? 's' : ''}
                          </span>
                        )}
                      </span>
                    )}
                    */}

                  </div>
                )}

                {/* Server Error State */}
                {msg.is503 ? (
                  <div className="bg-white text-red-600 border border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 rounded-xl p-3.5 text-xs space-y-2 shadow-subtle">
                    <div className="flex items-center gap-2 font-semibold">
                      <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-500 flex-shrink-0" />
                      <span>Server is Down</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => retryBotMessage?.(sessionId, msg.failedClientMessageId || msg.id, msg.failedText || '')}
                      className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm cursor-pointer mt-1"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Retry</span>
                    </button>
                  </div>
                ) : (
                  /* Standard Bubble Text */
                  <div
                    className={`rounded-xl px-4 py-2.5 text-xs leading-relaxed ${isUser
                      ? 'bg-[#2D4351] dark:bg-golden-500 text-white dark:text-black rounded-tr-none shadow-sm'
                      : 'bg-white dark:bg-black border border-[#E5E7EB] dark:border-gray-800 text-gray-900 dark:text-golden-300 rounded-tl-none shadow-subtle'
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
                {!isUser && msg.requestFulfilled === false && msg.collectionCancelled && (
                  <div role="status" className="mt-3 p-3 rounded-lg border border-amber-400 text-amber-800 dark:text-amber-200">
                    <p className="font-semibold">Chat cleared — this request was cancelled.</p>
                  </div>
                )}
                {!isUser && msg.timedOut && !msg.collectionCancelled && msg.timeoutOptions && (
                  <section className="mt-3 p-3 border rounded-lg text-sm" aria-label="Scraper timeout recovery">
                    <p className="font-semibold">Scraper stopped after five minutes without records.</p>
                    <p>Would you like to rerun it or try another compatible source?</p>
                    <ul className="my-2 space-y-1">{msg.timeoutOptions.scrapers.map(source => <li key={source.id}>
                      <strong>{source.name}:</strong> {source.description}
                      {source.id === msg.timeoutOptions?.recommendedSource && ' — Best compatible alternative for this request.'}
                      {!source.compatible && ' — Does not cover this request.'}
                    </li>)}</ul>
                    {!msg.timeoutOptions.recommendedSource && <p>No other configured scraper covers this record type and location.</p>}
                    <div className="flex gap-2 mt-2">
                      <button className="px-3 py-1 border rounded" onClick={() => onSendMessage(`Please rerun the ${msg.timeoutOptions?.retrySource} scraper for the same request.`)}>Rerun scraper</button>
                      {msg.timeoutOptions.recommendedSource && <button className="px-3 py-1 border rounded" onClick={() => onSendMessage(`Please use the ${msg.timeoutOptions?.recommendedSource} scraper for the same request.`)}>Try recommended scraper</button>}
                    </div>
                  </section>
                )}
                {!isUser && msg.records && msg.records.length > 0 && (
                  <div className="mt-2.5 bg-white rounded-xl border border-gray-200 overflow-hidden shadow-subtle">
                    <div className="px-3.5 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                      <span className="text-xs font-bold text-gray-800 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-green-600" />
                        {msg.deliveryKind === 'recovered' ? 'Recovered Data' : 'Extracted Lead Records'} ({msg.records.length})
                      </span>
                      {msg.total !== undefined && msg.total > msg.records.length && (
                        <span className="text-[10px] text-gray-500 font-mono">Total available: {msg.total}</span>
                      )}
                    </div>
                    <div className="max-h-72 overflow-y-auto">
                      <LeadTable leads={msg.records} compact={true} onSelectLead={setSelectedLead} />
                    </div>
                  </div>
                )}

                {/* Pending Action: Approve / Reject Buttons */}
                {/* Pending Action: Approve / Reject Buttons */}
                {!isUser && msg.pendingAction && msg.id === messages[messages.length - 1]?.id && (
                  <div className="mt-2.5 p-3 rounded-xl bg-white text-blue-900 border border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 text-xs space-y-2">
                    <div className="flex items-center gap-1.5 font-semibold text-blue-900 dark:text-blue-400">
                      <AlertCircle className="w-4 h-4 text-blue-600 dark:text-blue-500 flex-shrink-0" />
                      <span>Ready to scrape</span>
                    </div>
                    <p className="text-blue-800 dark:text-blue-600 text-[11px]">
                      {typeof msg.pendingAction === 'string'
                        ? msg.pendingAction
                        : msg.pendingAction?.label || 'The agent proposed running a targeted scrape. Would you like to proceed?'}
                    </p>
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => handleScrapeDecision('approve', msg.pendingAction?.proposal?.tool_call_id)}
                        disabled={isTyping}
                        title="Approve and start this scraper"
                        className="px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 text-white font-semibold text-xs transition-colors flex items-center gap-1 shadow-sm cursor-pointer"
                      >
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>{isTyping ? 'Starting…' : 'Action'}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleScrapeDecision('reject', msg.pendingAction?.proposal?.tool_call_id)}
                        disabled={isTyping}
                        className="px-3 py-1.5 rounded-lg bg-white border border-gray-300 hover:bg-gray-100 text-gray-700 font-semibold text-xs transition-colors cursor-pointer"
                      >
                        <span>Cancel</span>
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
                {!isUser && !msg.pendingAction && msg.proposedActions && msg.proposedActions.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
                      Proposed Next Actions:
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {msg.proposedActions.map((action, aIdx) => (
                        <div
                          key={aIdx}
                          className="flex items-center justify-between p-2 rounded-lg bg-white border border-blue-200 shadow-sm text-xs"
                        >
                          <div className="min-w-0 pr-2">
                            <span className="font-semibold text-gray-900 block truncate">{action.label}</span>
                            <span className="text-[10px] text-gray-400 font-mono">{action.actionType}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => (onExecuteAction ? onExecuteAction(action) : handleSend(`Execute ${action.label}`))}
                            className="px-2.5 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 text-[11px] font-medium flex items-center gap-1 transition-colors flex-shrink-0"
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
                  className={`text-[10px] text-gray-400 ${isUser ? 'text-right' : 'text-left'
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
              <Bot className="w-3.5 h-3.5 text-green-300" />
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
      <div className="p-3 border-t border-[#E5E7EB] dark:border-gray-800 bg-white dark:bg-black">
        <div className="relative flex items-center">
          <textarea
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your data requirement or ask our multi-agent intelligence..."
            rows={1}
            className="w-full bg-[#F8F9FA] dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 rounded-lg pl-3 pr-12 py-2.5 text-xs text-gray-900 dark:text-golden-100 placeholder:text-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500 focus:border-[#2D4351] dark:focus:border-golden-500 transition-colors resize-none overflow-y-auto"
          />
          <div className="absolute right-1.5 flex items-center gap-1">
            <button
              type="button"
              onClick={() => handleSend()}
              disabled={!inputText.trim()}
              className={`p-1.5 rounded-md transition-colors ${inputText.trim()
                ? 'bg-[#2D4351] dark:bg-golden-500 text-white dark:text-black hover:bg-[#20313C] dark:hover:bg-golden-600'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-600 cursor-not-allowed'
                }`}
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
      <LeadDrawer lead={selectedLead} isOpen={Boolean(selectedLead)} onClose={() => setSelectedLead(null)} />
    </div>
  );
};
