import React, { useState, useRef, useEffect } from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { AgentMessage } from '../../types';
import { Send, Paperclip, Bot, Sparkles, CornerDownLeft } from 'lucide-react';

interface AgentChatProps {
  sessionId: string;
  messages: AgentMessage[];
  onSendMessage: (text: string) => void;
  onInstantTrigger?: (scriptId: string) => void;
}

export const AgentChat: React.FC<AgentChatProps> = ({
  sessionId,
  messages,
  onSendMessage,
  onInstantTrigger,
}) => {
  const { currentUser } = useDataOps();
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
          <div className="w-8 h-8 rounded-lg bg-[#2D4351] text-white flex items-center justify-center">
            <Bot className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-gray-900">
                {currentUser.departmentName} AI Agent
              </span>
              <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                Online
              </span>
            </div>
            <p className="text-[11px] text-[#848485]">
              Autonomous 4-engine data operations specialist
            </p>
          </div>
        </div>

        {/* Status Indicator */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-emerald-600" />
            1-Click Trigger Active
          </span>
        </div>
      </div>

      {/* 4 Scraper Engines Toolbar */}
      <div className="bg-[#F8F9FA] border-b border-[#E5E7EB] px-3.5 py-2 flex items-center justify-between gap-2 overflow-x-auto">
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 whitespace-nowrap flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-indigo-500" />
          Click to Trigger:
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
                title={`Instant Trigger: Launch ${sc.name} immediately without delay`}
                className="text-[11px] font-semibold px-2.5 py-1 hover:bg-emerald-50 hover:text-emerald-800 text-gray-800 transition-colors flex items-center gap-1 border-r border-gray-100 cursor-pointer"
              >
                <span>{sc.icon}</span>
                <span>{sc.name}</span>
                <span className="text-[9px] bg-emerald-100 text-emerald-800 px-1 py-0.2 rounded font-mono font-bold ml-1">⚡ Trigger</span>
              </button>
              <button
                type="button"
                onClick={() => handleSend(`Targeting ${sc.fullName}. Please ask me what requirements you need.`)}
                title={`Interview Mode: Ask cross-questions about ${sc.name}`}
                className="text-[10px] font-medium px-2 py-1 text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors cursor-pointer"
              >
                💬 Chat
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#F8F9FA]/40">
        {messages.map(msg => {
          const isUser = msg.sender === 'user';
          return (
            <div
              key={msg.id}
              className={`flex gap-3 max-w-[85%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`}
            >
              {/* Avatar */}
              {isUser ? (
                <img
                  src={currentUser.avatar}
                  alt={currentUser.name}
                  className="w-7 h-7 rounded-full object-cover ring-1 ring-gray-200 flex-shrink-0"
                />
              ) : (
                <div className="w-7 h-7 rounded-full bg-[#2D4351] text-white flex items-center justify-center flex-shrink-0 text-xs shadow-sm">
                  <Bot className="w-3.5 h-3.5 text-emerald-300" />
                </div>
              )}

              {/* Bubble */}
              <div className="space-y-1.5">
                <div
                  className={`rounded-xl px-4 py-2.5 text-xs leading-relaxed ${
                    isUser
                      ? 'bg-[#2D4351] text-white rounded-tr-none'
                      : 'bg-white border border-[#E5E7EB] text-gray-900 rounded-tl-none shadow-subtle'
                  }`}
                >
                  <p>{msg.text}</p>
                </div>

                {/* Suggestions chips */}
                {msg.suggestions && msg.suggestions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {msg.suggestions.map(s => (
                      <button
                        key={s}
                        onClick={() => handleSend(s)}
                        className="text-[11px] px-2.5 py-1 rounded-full bg-white border border-gray-200 text-gray-700 hover:border-[#2D4351] hover:text-[#2D4351] transition-all shadow-subtle"
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
            placeholder="Type your data requirement (e.g. Commercial construction in Texas)..."
            className="w-full bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg pl-3 pr-20 py-2.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351] focus:border-[#2D4351]"
          />
          <div className="absolute right-1.5 flex items-center gap-1">
            <button
              type="button"
              className="p-1 text-gray-400 hover:text-gray-600 rounded"
              title="Attach document/spec"
            >
              <Paperclip className="w-4 h-4" />
            </button>
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
