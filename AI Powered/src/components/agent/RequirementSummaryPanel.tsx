import React from 'react';
import { Requirement } from '../../types';
import { CheckCircle2, Sparkles, ArrowRight, Eye, RefreshCw, AlertCircle, Play } from 'lucide-react';

interface RequirementSummaryPanelProps {
  requirement: Requirement;
  onConfirm: () => void;
  onViewJob?: (jobId?: string) => void;
  onViewResults?: () => void;
}

export const RequirementSummaryPanel: React.FC<RequirementSummaryPanelProps> = ({
  requirement,
  onConfirm,
  onViewJob,
  onViewResults,
}) => {
  const isRunning = requirement.status === 'generating' || requirement.status === 'running';
  const isCompleted = requirement.status === 'completed';
  const isFailed = requirement.status === 'failed';
  const isReady =
    requirement.status === 'ready_for_confirmation' ||
    requirement.status === 'confirmed' ||
    ((requirement.completionPercentage || 0) >= 80 && !isRunning && !isCompleted && !isFailed);

  const scriptKey = ((requirement as any).selectedScript || (requirement as any).scriptId || '').toLowerCase();
  const indLower = (requirement.industry || '').toLowerCase();
  const locLower = (requirement.location || '').toLowerCase();

  const selectedEngine =
    (requirement as any).selectedScriptName ||
    (requirement as any).scriptName ||
    (scriptKey === 'bonfire' || locLower.includes('dallas') || indLower.includes('bonfire')
      ? 'Dallas City Hall Bonfire Scraper'
      : scriptKey === 'dasny' || indLower.includes('dasny')
      ? 'DASNY RFP & Bid Opportunities Scraper'
      : scriptKey === 'jwiz' || indLower.includes('jwiz') || indLower.includes('directory')
      ? 'JWiz Commercial Directory Scraper'
      : scriptKey === 'nyscr' || indLower.includes('nyscr') || locLower.includes('albany')
      ? 'NYSCR State Contract Reporter Scraper'
      : indLower.includes('construction')
      ? 'DASNY RFP & Bid Opportunities Scraper'
      : 'Auto-detected Scraper Engine');

  let volumeText = requirement.quantity ? `${requirement.quantity.toLocaleString()} target records` : '20 target records';
  if (isCompleted) {
    const verified = (requirement as any).verifiedRecords || requirement.quantity || 0;
    volumeText = `${verified.toLocaleString()} verified records`;
  } else if (isRunning) {
    volumeText = requirement.quantity
      ? `${requirement.quantity.toLocaleString()} target records (Extracting...)`
      : 'Target records (Extracting...)';
  } else if (isFailed) {
    volumeText = requirement.quantity
      ? `${requirement.quantity.toLocaleString()} target records (Failed)`
      : 'Extraction Failed';
  } else if (isReady) {
    volumeText = requirement.quantity
      ? `${requirement.quantity.toLocaleString()} target records (Ready to confirm)`
      : '20 target records (Ready to confirm)';
  }

  const fields = [
    { label: 'Scraper Engine', value: selectedEngine, isHighlight: true },
    { label: 'Category / Scope', value: requirement.industry },
    { label: 'Target Location', value: requirement.location },
    {
      label: 'Extraction Volume',
      value: volumeText,
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

  // Header status badge
  let badgeClass = 'bg-gray-50 text-gray-600 border border-gray-200';
  let badgeLabel = 'SPECIFICATION IN PROGRESS';
  if (isRunning) {
    badgeClass = 'bg-indigo-50 text-indigo-700 border border-indigo-200 animate-pulse';
    badgeLabel = 'RUNNING / IN PROGRESS';
  } else if (isCompleted) {
    badgeClass = 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    badgeLabel = 'COMPLETED';
  } else if (isFailed) {
    badgeClass = 'bg-rose-50 text-rose-700 border border-rose-200';
    badgeLabel = 'FAILED';
  } else if (isReady) {
    badgeClass = 'bg-amber-50 text-amber-700 border border-amber-200';
    badgeLabel = 'READY FOR CONFIRMATION';
  }

  // Progress display
  let progressPercentage = requirement.completionPercentage || 0;
  let progressText = `${progressPercentage}% complete`;
  let progressBarColor = 'bg-[#2D4351]';

  if (isRunning) {
    progressPercentage = Math.max(25, Math.min(95, requirement.completionPercentage || 35));
    progressText = `In Progress (${progressPercentage}%)`;
    progressBarColor = 'bg-indigo-600';
  } else if (isCompleted) {
    progressPercentage = 100;
    progressText = '100% complete';
    progressBarColor = 'bg-emerald-500';
  } else if (isFailed) {
    progressPercentage = 0;
    progressText = 'Failed (0%)';
    progressBarColor = 'bg-rose-500';
  } else if (isReady) {
    progressPercentage = 100;
    progressText = '100% complete';
    progressBarColor = 'bg-emerald-500';
  }

  // Bottom action CTA
  let ctaButton: React.ReactNode = null;
  let ctaHelperText: string | null = null;

  if (isRunning) {
    ctaButton = (
      <button
        onClick={() => (onViewJob ? onViewJob((requirement as any).jobId) : onConfirm())}
        className="w-full py-2.5 px-4 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm bg-indigo-600 text-white hover:bg-indigo-700 cursor-pointer"
      >
        <Eye className="w-4 h-4 text-indigo-200" />
        <span>View Job</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    );
    ctaHelperText = 'Your extraction is active. Click to monitor execution logs in real time.';
  } else if (isCompleted) {
    ctaButton = (
      <button
        onClick={() => (onViewResults ? onViewResults() : onConfirm())}
        className="w-full py-2.5 px-4 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm bg-emerald-600 text-white hover:bg-emerald-700 cursor-pointer"
      >
        <CheckCircle2 className="w-4 h-4 text-emerald-200" />
        <span>View Results</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    );
    ctaHelperText = 'Extraction completed & verified in PostgreSQL. Click to browse records.';
  } else if (isFailed) {
    ctaButton = (
      <button
        onClick={() => (onViewJob ? onViewJob((requirement as any).jobId) : onConfirm())}
        className="w-full py-2.5 px-4 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm bg-rose-600 text-white hover:bg-rose-700 cursor-pointer"
      >
        <AlertCircle className="w-4 h-4 text-rose-200" />
        <span>Retry / View Details</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    );
    ctaHelperText = 'The extraction job encountered an error during execution.';
  } else if (isReady) {
    ctaButton = (
      <button
        onClick={onConfirm}
        className="w-full py-2.5 px-4 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm bg-[#2D4351] text-white hover:bg-[#20313C] cursor-pointer"
      >
        <Sparkles className="w-4 h-4 text-emerald-400" />
        <span>Confirm & Generate Data</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    );
    ctaHelperText = 'Specification complete. Click to launch autonomous scraper.';
  } else {
    ctaButton = (
      <button
        disabled
        className="w-full py-2.5 px-4 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm bg-gray-100 text-gray-400 cursor-not-allowed"
      >
        <Sparkles className="w-4 h-4 text-gray-400" />
        <span>Confirm & Generate Data</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    );
    ctaHelperText = 'Complete the chat cross-questions to unlock generation';
  }

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 flex flex-col h-full shadow-card">
      {/* Header */}
      <div className="border-b border-[#E5E7EB] pb-3 mb-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
            DATA REQUIREMENT
          </span>
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${badgeClass}`}>
            {badgeLabel}
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

      {/* Progress & CTA */}
      <div className="border-t border-[#E5E7EB] pt-4 mt-4">
        <div className="flex items-center justify-between text-xs font-medium text-gray-700 mb-1.5">
          <span>Requirement Progress</span>
          <span className="font-semibold text-gray-900">
            {progressText}
          </span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden mb-4">
          <div
            className={`h-full transition-all duration-500 rounded-full ${progressBarColor}`}
            style={{ width: `${Math.min(100, Math.max(0, progressPercentage))}%` }}
          />
        </div>

        {ctaButton}

        {ctaHelperText && (
          <p className="text-[11px] text-gray-500 text-center mt-2">
            {ctaHelperText}
          </p>
        )}
      </div>
    </div>
  );
};
