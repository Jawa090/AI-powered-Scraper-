import React, { useState } from 'react';
import { Modal } from '../common/Modal';
import { Lead } from '../../types';
import { Send, CheckCircle2, Loader2, Sparkles, Tag } from 'lucide-react';

interface BulkEmailModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLeads: Lead[];
  onSendBulk: (leadIds: string[], subject: string, body: string) => Promise<void>;
}

export const BulkEmailModal: React.FC<BulkEmailModalProps> = ({
  isOpen,
  onClose,
  selectedLeads,
  onSendBulk,
}) => {
  const [subject, setSubject] = useState('Data Operations Intelligence for {{company_name}}');
  const [body, setBody] = useState(`Hi {{first_name}},\n\nI noticed {{company_name}} has been expanding in the enterprise space. Our platform streamlines operational data pipelines and customer verification without engineering bottlenecks.\n\nAre you open to a brief 10-minute briefing this week?\n\nBest regards,\nOperations & Growth Team`);
  const [sendingState, setSendingState] = useState<'idle' | 'sending' | 'completed'>('idle');
  const [sentCount, setSentCount] = useState(0);

  const handleStartSending = async () => {
    setSendingState('sending');
    setSentCount(0);

    const total = selectedLeads.length;
    let current = 0;

    const interval = setInterval(() => {
      current += Math.max(1, Math.floor(total / 4));
      if (current >= total) {
        current = total;
        clearInterval(interval);
        setSentCount(total);
        setSendingState('completed');

        // Apply bulk update to global state
        onSendBulk(
          selectedLeads.map(l => l.id),
          subject,
          body
        );
      } else {
        setSentCount(current);
      }
    }, 450);
  };

  const insertVariable = (variable: string) => {
    setBody(prev => prev + ' ' + variable);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (sendingState !== 'sending') onClose();
      }}
      title="Bulk Email Outreach Sequence"
      subtitle={`Targeting ${selectedLeads.length} selected lead${selectedLeads.length > 1 ? 's' : ''}`}
      maxWidth="xl"
    >
      <div className="space-y-4">
        {sendingState === 'idle' && (
          <>
            {/* Variable Pills */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold text-gray-700">
                  Insert Personalization Variables:
                </label>
                <span className="text-[11px] text-gray-500">Click to append</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {['{{first_name}}', '{{company_name}}', '{{title}}', '{{location}}'].map(v => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => insertVariable(v)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-[#EAEFF2] text-[#2D4351] text-xs font-mono font-medium hover:bg-[#2D4351] hover:text-white transition-colors"
                  >
                    <Tag className="w-3 h-3" />
                    {v}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Subject</label>
              <input
                type="text"
                value={subject}
                onChange={e => setSubject(e.target.value)}
                className="w-full text-xs p-2.5 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">
                Sequence Body (Supports Markdown)
              </label>
              <textarea
                rows={7}
                value={body}
                onChange={e => setBody(e.target.value)}
                className="w-full text-xs p-2.5 bg-white border border-[#E5E7EB] rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-[#2D4351] leading-relaxed"
              />
            </div>

            {/* Recipient preview */}
            <div className="p-3 bg-[#F8F9FA] rounded-lg border border-[#E5E7EB] text-xs text-gray-600">
              <span className="font-semibold text-gray-800">Recipients preview: </span>
              {selectedLeads.slice(0, 3).map(l => l.name).join(', ')}
              {selectedLeads.length > 3 && ` and ${selectedLeads.length - 3} others`}
            </div>

            <div className="flex justify-end gap-2.5 pt-2 border-t border-gray-100">
              <button
                type="button"
                onClick={onClose}
                className="px-3.5 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded-lg border border-gray-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleStartSending}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-[#2D4351] hover:bg-[#20313C] rounded-lg flex items-center gap-1.5 shadow-sm"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send to {selectedLeads.length} leads</span>
              </button>
            </div>
          </>
        )}

        {sendingState === 'sending' && (
          <div className="py-8 px-4 text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 mx-auto flex items-center justify-center animate-spin">
              <Loader2 className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-gray-900">
                Dispatching Personalized Sequences...
              </h4>
              <p className="text-xs text-gray-500 mt-1">
                Sending {sentCount} / {selectedLeads.length}
              </p>
            </div>

            <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden max-w-md mx-auto">
              <div
                className="h-full bg-[#2D4351] transition-all duration-300 rounded-full"
                style={{ width: `${(sentCount / selectedLeads.length) * 100}%` }}
              />
            </div>
          </div>
        )}

        {sendingState === 'completed' && (
          <div className="py-8 px-4 text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 mx-auto flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-gray-900">
                {sentCount} Emails Successfully Sent!
              </h4>
              <p className="text-xs text-gray-500 mt-1">
                Leads have been updated to "Emailed" and logged to your activity timeline.
              </p>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2 text-xs font-semibold text-white bg-[#2D4351] hover:bg-[#20313C] rounded-lg shadow-sm"
            >
              Done & Return to Workspace
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
};
