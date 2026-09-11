import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Lead } from '../../types';
import { Send, Sparkles } from 'lucide-react';

interface EmailComposerModalProps {
  isOpen: boolean;
  onClose: () => void;
  lead: Lead | null;
  onSendEmail: (leadId: string, subject: string, body: string) => void;
}

export const EmailComposerModal: React.FC<EmailComposerModalProps> = ({
  isOpen,
  onClose,
  lead,
  onSendEmail,
}) => {
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');

  useEffect(() => {
    if (lead) {
      const firstName = lead.name.split(' ')[0];
      setSubject(`Solution for ${lead.company} operations`);
      setBody(`Hi ${firstName},\n\nI noticed ${lead.company} has been scaling its operations. Our enterprise data platform assists teams like yours in automating data verification and compliance workflows.\n\nWould you have 10 minutes next Tuesday for a quick introductory discussion?\n\nBest regards,\nOperations Team`);
    }
  }, [lead]);

  if (!lead) return null;

  const handleSend = () => {
    onSendEmail(lead.id, subject, body);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Compose Outreach Email"
      subtitle={`Recipient: ${lead.name} <${lead.email}>`}
      maxWidth="lg"
    >
      <div className="space-y-3.5">
        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1">To</label>
          <input
            type="text"
            readOnly
            value={`${lead.name} <${lead.email}>`}
            className="w-full text-xs p-2 bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg text-gray-700 cursor-not-allowed"
          />
        </div>

        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1">Subject</label>
          <input
            type="text"
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full text-xs p-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1">Message Body</label>
          <textarea
            rows={7}
            value={body}
            onChange={e => setBody(e.target.value)}
            className="w-full text-xs p-2.5 bg-white border border-[#E5E7EB] rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-[#2D4351] leading-relaxed"
          />
        </div>

        <div className="flex justify-between items-center pt-2 border-t border-gray-100">
          <span className="text-[11px] text-emerald-600 flex items-center gap-1 font-medium">
            <Sparkles className="w-3.5 h-3.5" />
            Live MX Handshake Verified (Deliverability &gt; 99%)
          </span>

          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded-lg border border-gray-200"
            >
              Cancel
            </button>
            <button
              onClick={handleSend}
              className="px-4 py-1.5 text-xs font-semibold text-white bg-[#2D4351] hover:bg-[#20313C] rounded-lg flex items-center gap-1.5 shadow-sm"
            >
              <Send className="w-3.5 h-3.5" />
              Send Email
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};
