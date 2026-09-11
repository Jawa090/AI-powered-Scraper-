import React from 'react';
import { Modal } from '../common/Modal';
import { Requirement } from '../../types';
import { Sparkles, CheckCircle2, ShieldCheck, ArrowRight } from 'lucide-react';

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  requirement: Requirement;
  onConfirm: () => void;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  onClose,
  requirement,
  onConfirm,
}) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Confirm Data Requirement"
      subtitle="Please review your requirement before starting data generation."
      maxWidth="lg"
    >
      <div className="space-y-4">
        <div className="p-4 bg-[#F8F9FA] rounded-lg border border-[#E5E7EB] space-y-2.5">
          <div className="flex justify-between text-xs">
            <span className="text-gray-500 font-medium">Scraper Engine:</span>
            <span className="text-indigo-600 font-bold">
              {(requirement as any).selectedScriptName || 'Autonomous Scraper Engine'}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-500 font-medium">Target Scope:</span>
            <span className="text-gray-900 font-semibold">{requirement.industry}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-500 font-medium">Target Region:</span>
            <span className="text-gray-900 font-semibold">{requirement.location}</span>
          </div>
          <div className="flex justify-between text-xs pt-2 border-t border-gray-200">
            <span className="text-gray-700 font-semibold">Requested Volume:</span>
            <span className="text-emerald-700 font-bold">
              {requirement.quantity ? requirement.quantity.toLocaleString() : '20'} Verified Records
            </span>
          </div>
        </div>

        <div className="flex items-start gap-2.5 p-3 bg-blue-50/70 border border-blue-100 rounded-lg">
          <ShieldCheck className="w-4 h-4 text-blue-700 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-blue-900 leading-relaxed">
            DataOps autonomous agent will execute multi-layer spatial discovery, MX mailbox verification, and cross-department deduplication. Data will be made immediately available inside the platform.
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-semibold text-gray-700 hover:bg-gray-100 transition-colors border border-gray-200"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <span>Confirm & Start Generation</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </Modal>
  );
};
