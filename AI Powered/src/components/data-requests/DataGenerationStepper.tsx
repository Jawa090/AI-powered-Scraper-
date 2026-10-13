import React from 'react';
import { Job } from '../../types';
import {
  CheckCircle2,
  Clock,
  Database,
  ArrowRight,
  ShieldCheck,
  AlertTriangle,
  Loader2,
  ListFilter,
  FileCheck2,
} from 'lucide-react';

interface DataGenerationStepperProps {
  job: Job;
  onViewLeads: () => void;
  onViewDataset: () => void;
}

export const DataGenerationStepper: React.FC<DataGenerationStepperProps> = ({
  job,
  onViewLeads,
  onViewDataset,
}) => {
  const steps = [
    'Understanding requirement',
    'Selecting workflow',
    'Collecting companies',
    'Finding contacts',
    'Finding emails',
    'Verifying data',
    'Deduplicating',
    'Preparing dataset',
  ];

  const currentIdx = steps.findIndex(s => s.toLowerCase() === job.currentStep.toLowerCase());
  const isCompleted = job.status === 'Completed' || job.progress >= 100;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Top Status Card */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E5E7EB] pb-5 mb-5">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-gray-900">{job.name}</h2>
              <span
                className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${
                  isCompleted
                    ? 'bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800'
                    : 'bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 animate-pulse'
                }`}
              >
                {isCompleted ? 'COMPLETED' : 'RUNNING'}
              </span>
            </div>
            <p className="text-xs text-[#848485] mt-1">
              Job ID: <span className="font-mono text-gray-700">{job.id}</span> • Department:{' '}
              <span className="font-semibold text-gray-900">{job.departmentName}</span> • Started:{' '}
              <span>{job.startedAt}</span>
            </p>
          </div>

          <div className="text-right">
            <span className="text-2xl font-black text-[#2D4351] font-mono">
              {job.progress}%
            </span>
            <p className="text-[11px] text-[#848485]">Overall Progress</p>
          </div>
        </div>

        {/* Big Progress Bar */}
        <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden mb-6">
          <div
            className={`h-full transition-all duration-500 rounded-full ${
              isCompleted ? 'bg-[#26619C]' : 'bg-[#2D4351]'
            }`}
            style={{ width: `${Math.min(100, job.progress)}%` }}
          />
        </div>

        {/* Live Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 p-4 bg-[#F8F9FA] rounded-xl border border-[#E5E7EB]">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
              Records Found
            </span>
            <p className="text-base font-bold text-gray-900 font-mono mt-0.5">
              {job.recordsFound.toLocaleString()} / {job.totalTarget.toLocaleString()}
            </p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
              Verified Records
            </span>
            <p className="text-base font-bold text-green-600 font-mono mt-0.5">
              {job.verifiedCount.toLocaleString()}
            </p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
              Deduplicated
            </span>
            <p className="text-base font-bold text-blue-600 font-mono mt-0.5">
              {job.duplicatesCount}
            </p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
              Skipped / Errors
            </span>
            <p className="text-base font-bold text-gray-500 font-mono mt-0.5">
              {job.errorsCount}
            </p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">
              Elapsed Time
            </span>
            <p className="text-base font-bold text-gray-900 font-mono mt-0.5">
              {job.duration}
            </p>
          </div>
        </div>
      </div>

      {/* Multi-step Pipeline Visualizer */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card">
        <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-4">
          Pipeline Execution Stepper
        </h3>

        <div className="space-y-3">
          {steps.map((step, index) => {
            const isStepCompleted = isCompleted || index < currentIdx;
            const isStepActive = !isCompleted && index === currentIdx;

            return (
              <div
                key={step}
                className={`p-3 rounded-lg border transition-all flex items-center justify-between ${
                  isStepCompleted
                    ? 'bg-[#E6F0FA]/50 border-[#B3D4F5] text-[#1E4E7C] dark:bg-[#1E4E7C]/10 dark:border-[#26619C]/30 dark:text-[#60A5FA]'
                    : isStepActive
                    ? 'bg-[#EAEFF2] border-[#2D4351] text-[#2D4351] ring-1 ring-[#2D4351] dark:bg-[#2D4351] dark:text-golden-500 dark:border-golden-500 dark:ring-golden-500'
                    : 'bg-[#F8F9FA]/40 border-gray-200 text-gray-400 dark:bg-gray-900/40 dark:border-gray-800'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="flex items-center justify-center">
                    {isStepCompleted ? (
                      <CheckCircle2 className="w-5 h-5 text-[#26619C] dark:text-[#60A5FA]" />
                    ) : isStepActive ? (
                      <Loader2 className="w-5 h-5 text-[#2D4351] dark:text-golden-500 animate-spin" />
                    ) : (
                      <span className="w-5 h-5 rounded-full border border-gray-300 flex items-center justify-center text-[10px] font-mono">
                        {index + 1}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-xs font-semibold">{step}</span>
                    {isStepActive && (
                      <p className="text-[11px] text-gray-600">Active autonomous worker executing...</p>
                    )}
                  </div>
                </div>

                <span className="text-[11px] font-mono font-medium">
                  {isStepCompleted ? 'DONE' : isStepActive ? 'PROCESSING' : 'QUEUED'}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Completion Banner with Action Buttons */}
      {isCompleted && (
        <div className="bg-[#E6F0FA] border border-[#B3D4F5] dark:bg-[#1E4E7C]/20 dark:border-[#26619C]/30 rounded-xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm animate-in fade-in">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-[#D1E4F9] text-[#1E4E7C] dark:bg-[#26619C]/30 dark:text-[#60A5FA] flex items-center justify-center flex-shrink-0">
              <FileCheck2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-[#1E4E7C] dark:text-[#60A5FA]">Dataset Ready</h3>
              <p className="text-xs text-[#26619C] dark:text-[#60A5FA]/80">
                {job.verifiedCount.toLocaleString()} leads successfully generated and verified. Ready for sales calling and email outreach.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button
              onClick={onViewLeads}
              className="flex-1 sm:flex-none px-4 py-2 text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-lg flex items-center justify-center gap-1.5 shadow-sm transition-colors"
            >
              <span>View Leads</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onViewDataset}
              className="flex-1 sm:flex-none px-4 py-2 text-xs font-semibold bg-white dark:bg-black border border-[#93C5FD] dark:border-[#26619C] text-[#1E4E7C] dark:text-[#60A5FA] hover:bg-[#D1E4F9]/50 dark:hover:bg-[#1E4E7C]/20 rounded-lg transition-colors"
            >
              View Dataset
            </button>
          </div>
        </div>
      )}

      {/* Live Terminal Logs */}
      <div className="bg-[#111827] rounded-xl p-4 text-xs font-mono text-gray-300 shadow-card">
        <div className="flex items-center justify-between border-b border-gray-800 pb-2 mb-3">
          <span className="text-[10px] uppercase tracking-wider text-gray-400 font-bold">
            Live Worker Telemetry
          </span>
          <span className="text-[10px] text-green-400 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Socket Connected
          </span>
        </div>

        <div className="space-y-1.5 max-h-44 overflow-y-auto">
          {job.logs.map((log, i) => (
            <div key={i} className="flex items-start gap-2 leading-relaxed">
              <span className="text-gray-500 text-[11px] whitespace-nowrap">[{log.timestamp}]</span>
              <span
                className={`text-[10px] px-1 rounded uppercase font-bold ${
                  log.level === 'warn'
                    ? 'bg-blue-900/60 text-blue-300'
                    : log.level === 'error'
                    ? 'bg-red-900/60 text-red-300'
                    : 'bg-gray-800 text-gray-400'
                }`}
              >
                {log.level}
              </span>
              <span className="text-gray-200">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
