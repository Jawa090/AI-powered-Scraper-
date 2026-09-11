import React from 'react';
import { Requirement } from '../../types';
import { CheckCircle2, Circle, Sparkles, ArrowRight, ShieldCheck } from 'lucide-react';

interface RequirementSummaryPanelProps {
  requirement: Requirement;
  onConfirm: () => void;
}

export const RequirementSummaryPanel: React.FC<RequirementSummaryPanelProps> = ({
  requirement,
  onConfirm,
}) => {
  const isReady =
    requirement.status === 'ready_for_confirmation' ||
    requirement.completionPercentage >= 100;

  const selectedEngine =
    (requirement as any).selectedScriptName ||
    (requirement.industry?.toLowerCase().includes('dallas') || requirement.industry?.toLowerCase().includes('bonfire')
      ? 'Dallas City Hall Bonfire Scraper'
      : requirement.industry?.toLowerCase().includes('dasny')
      ? 'DASNY RFP Scraper'
      : requirement.industry?.toLowerCase().includes('jwiz') || requirement.industry?.toLowerCase().includes('directory')
      ? 'JWiz Commercial Directory Scraper'
      : requirement.industry?.toLowerCase().includes('nyscr')
      ? 'NYSCR State Contracts Scraper'
      : 'Auto-detected Scraper Engine');

  const fields = [
    { label: 'Scraper Engine', value: selectedEngine, isHighlight: true },
    { label: 'Category / Scope', value: requirement.industry },
    { label: 'Target Location', value: requirement.location },
    {
      label: 'Extraction Volume',
      value: requirement.quantity ? `${requirement.quantity.toLocaleString()} verified records` : 'Not specified',
    },
  ];

  const checklist = [
    { key: 'companyName', label: 'Company / Project Name' },
    { key: 'contactName', label: 'Procurement / Contact Officer' },
    { key: 'jobTitle', label: 'Reference # / Category' },
    { key: 'email', label: 'Verified Email / Mailto' },
    { key: 'phone', label: 'Phone / Direct Dial' },
    { key: 'website', label: 'Portal URL & Detail Spec' },
  ];

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 flex flex-col h-full shadow-card">
      {/* Header */}
      <div className="border-b border-[#E5E7EB] pb-3 mb-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
            DATA REQUIREMENT
          </span>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
              isReady
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-amber-50 text-amber-700 border border-amber-200'
            }`}
          >
            {isReady ? 'READY FOR CONFIRMATION' : 'Cross-questioning in progress'}
          </span>
        </div>
        <h3 className="text-sm font-semibold text-gray-900 mt-1">
          Structured Intelligence Spec
        </h3>
      </div>

      {/* Requirement Fields */}
      <div className="space-y-3 flex-1 overflow-y-auto pr-1">
        {fields.map(f => {
          const isSet = f.value && f.value !== 'Not specified';
          return (
            <div key={f.label} className="border-b border-gray-50 pb-2">
              <span className="text-[11px] text-[#848485] block font-medium">
                {f.label}
              </span>
              <span
                className={`text-xs font-semibold mt-0.5 block ${
                  (f as any).isHighlight
                    ? 'text-indigo-600 font-bold'
                    : isSet
                    ? 'text-gray-900'
                    : 'text-gray-400 italic'
                }`}
              >
                {f.value || 'Not specified'}
              </span>
            </div>
          );
        })}

        {/* Required Data Checklist */}
        <div className="pt-2">
          <span className="text-[11px] font-semibold text-gray-700 uppercase tracking-wider block mb-2">
            Target Schema & Attributes:
          </span>
          <div className="grid grid-cols-2 gap-1.5">
            {checklist.map(item => (
              <div key={item.key} className="flex items-center gap-1.5 text-xs text-gray-700">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                <span className="truncate">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Progress & Confirmation CTA */}
      <div className="border-t border-[#E5E7EB] pt-4 mt-4">
        <div className="flex items-center justify-between text-xs font-medium text-gray-700 mb-1.5">
          <span>Requirement Progress</span>
          <span className="font-semibold text-gray-900">
            {requirement.completionPercentage}% complete
          </span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden mb-4">
          <div
            className={`h-full transition-all duration-500 rounded-full ${
              isReady ? 'bg-emerald-500' : 'bg-[#2D4351]'
            }`}
            style={{ width: `${Math.min(100, requirement.completionPercentage)}%` }}
          />
        </div>

        <button
          onClick={onConfirm}
          disabled={!isReady}
          className={`w-full py-2.5 px-4 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm ${
            isReady
              ? 'bg-[#2D4351] text-white hover:bg-[#20313C] cursor-pointer'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
          }`}
        >
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <span>Confirm & Generate Data</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>

        {!isReady && (
          <p className="text-[11px] text-gray-500 text-center mt-2">
            Complete the chat cross-questions to unlock generation
          </p>
        )}
      </div>
    </div>
  );
};
