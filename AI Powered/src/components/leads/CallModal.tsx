import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Lead, LeadStatus } from '../../types';
import { Phone, PhoneCall, PhoneOff, Clock, Calendar, Check, AlertCircle } from 'lucide-react';

interface CallModalProps {
  isOpen: boolean;
  onClose: () => void;
  lead: Lead | null;
  onSaveCall: (leadId: string, outcome: LeadStatus, notes: string, nextFollowUp?: string) => void;
}

export const CallModal: React.FC<CallModalProps> = ({
  isOpen,
  onClose,
  lead,
  onSaveCall,
}) => {
  const [callState, setCallState] = useState<'dialing' | 'connected' | 'completed'>('dialing');
  const [timer, setTimer] = useState(0);
  const [selectedOutcome, setSelectedOutcome] = useState<LeadStatus>('Interested');
  const [notes, setNotes] = useState('');
  const [followUpDate, setFollowUpDate] = useState('2026-09-15');

  useEffect(() => {
    if (isOpen) {
      setCallState('dialing');
      setTimer(0);
      setSelectedOutcome('Interested');
      setNotes('');

      const connectTimer = setTimeout(() => {
        setCallState('connected');
      }, 1400);

      return () => clearTimeout(connectTimer);
    }
  }, [isOpen]);

  useEffect(() => {
    let interval: any;
    if (isOpen && callState === 'connected') {
      interval = setInterval(() => {
        setTimer(t => t + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isOpen, callState]);

  if (!lead) return null;

  const formatTimer = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const outcomes: { status: LeadStatus; label: string; color: string }[] = [
    { status: 'Interested', label: 'Interested', color: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100' },
    { status: 'Follow Up', label: 'Follow Up Required', color: 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100' },
    { status: 'Called', label: 'No Answer / Left VM', color: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100' },
    { status: 'Not Interested', label: 'Not Interested', color: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100' },
  ];

  const handleSave = () => {
    onSaveCall(lead.id, selectedOutcome, notes, selectedOutcome === 'Follow Up' || selectedOutcome === 'Interested' ? followUpDate : undefined);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Outbound Call: ${lead.name}`}
      subtitle={`${lead.title} at ${lead.company}`}
      maxWidth="lg"
    >
      <div className="space-y-4">
        {/* Call Banner */}
        <div className="bg-[#F8F9FA] border border-[#E5E7EB] rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center ${
                callState === 'connected'
                  ? 'bg-emerald-100 text-emerald-700 animate-pulse'
                  : 'bg-blue-100 text-blue-700 animate-bounce'
              }`}
            >
              {callState === 'connected' ? (
                <PhoneCall className="w-5 h-5" />
              ) : (
                <Phone className="w-5 h-5" />
              )}
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-900">
                {lead.phone || '+1 (512) 849-2041'}
              </p>
              <p className="text-[11px] text-gray-500">
                {callState === 'dialing'
                  ? 'Initiating connection via direct dial...'
                  : 'Call in progress (HQ Line)'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-semibold px-2.5 py-1 bg-white border border-gray-200 rounded-md text-gray-700">
              {formatTimer(timer)}
            </span>
            {callState === 'connected' && (
              <button
                onClick={() => setCallState('completed')}
                className="px-2.5 py-1 text-xs font-semibold bg-rose-50 border border-rose-200 text-rose-700 rounded-md hover:bg-rose-100 flex items-center gap-1"
              >
                <PhoneOff className="w-3.5 h-3.5" />
                End
              </button>
            )}
          </div>
        </div>

        {/* Outcome Selector */}
        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1.5">
            Select Call Outcome
          </label>
          <div className="grid grid-cols-2 gap-2">
            {outcomes.map(o => {
              const isSelected = selectedOutcome === o.status;
              return (
                <button
                  key={o.status}
                  type="button"
                  onClick={() => setSelectedOutcome(o.status)}
                  className={`px-3 py-2 rounded-lg text-xs font-semibold border transition-all text-left flex items-center justify-between ${
                    isSelected
                      ? 'border-[#2D4351] ring-1 ring-[#2D4351] bg-[#EAEFF2] text-[#2D4351]'
                      : o.color
                  }`}
                >
                  <span>{o.label}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-[#2D4351]" />}
                </button>
              );
            })}
          </div>
        </div>

        {/* Call Notes */}
        <div>
          <label className="text-xs font-semibold text-gray-700 block mb-1">
            Call Notes & Context
          </label>
          <textarea
            rows={3}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Discussed commercial construction project requirements, verified company size, scheduled follow-up demo..."
            className="w-full text-xs p-2.5 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

        {/* Follow up date */}
        {(selectedOutcome === 'Follow Up' || selectedOutcome === 'Interested') && (
          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              Scheduled Follow-up Date
            </label>
            <div className="relative">
              <Calendar className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="date"
                value={followUpDate}
                onChange={e => setFollowUpDate(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
              />
            </div>
          </div>
        )}

        {/* Footer Actions */}
        <div className="flex justify-end gap-2.5 pt-2 border-t border-gray-100">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 rounded-lg border border-gray-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-1.5 text-xs font-semibold text-white bg-[#2D4351] hover:bg-[#20313C] rounded-lg shadow-sm"
          >
            Save Call & Update Pipeline
          </button>
        </div>
      </div>
    </Modal>
  );
};
