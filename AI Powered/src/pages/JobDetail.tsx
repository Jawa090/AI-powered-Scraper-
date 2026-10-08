import React from 'react';
import { apiService } from '../services/api.service';
import { useDataOps } from '../context/DataOpsContext';
import { StatusBadge } from '../components/common/StatusBadge';
import { ArrowLeft, RefreshCw, XCircle, Database, CheckCircle2, AlertCircle } from 'lucide-react';

interface JobDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const JobDetail: React.FC<JobDetailProps> = ({ id, onNavigate }) => {
  const { getLiveJob, showToast } = useDataOps();
  const job = getLiveJob(id);

  if (!job) {
    return <div className="p-8 text-center text-xs text-gray-500">Job record not found.</div>;
  }

  const handleRetry = () => {
    onNavigate('/agent');
    showToast('Request a new scrape', 'Review the criteria and approve a new request in the chat.', 'info');
  };

  const handleCancel = async () => {
    const ok = await apiService.cancelJob(job.id);
    showToast(ok ? 'Cancellation requested' : 'Cancellation failed', ok ? 'The server accepted the cancellation request.' : 'The job could not be cancelled.', ok ? 'info' : 'error');
  };

  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/jobs')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Jobs</span>
      </button>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-6">
        {job.status === 'WaitingForUser' && <div className="border border-amber-300 rounded-lg p-4 text-sm">
          <p>{(job as any).waitingFor || 'Complete verification in the scraper browser, then resume.'}</p>
          {(job as any).captchaViewerUrl && <a className="underline" href={(job as any).captchaViewerUrl} target="_blank" rel="noreferrer">Open verification browser</a>}
          <button className="ml-3 border rounded px-3 py-2" onClick={() => { void apiService.resumeJob(job.id).then(() => showToast('Resume requested', 'The worker will check the browser state.', 'info')).catch(error => showToast('Resume failed', error.message, 'error')); }}>Verification completed — resume</button>
        </div>}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E5E7EB] pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900">{job.name}</h1>
              <StatusBadge status={job.status} />
            </div>
            <p className="text-xs text-[#848485] mt-1">
              Job ID: <span className="font-mono text-gray-700">{job.id}</span> • Department:{' '}
              <span className="font-semibold text-gray-800">{job.departmentName}</span> • Type: {job.type}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRetry}
              className="px-3 py-1.5 rounded-lg border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-50 flex items-center gap-1"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </button>
            <button
              onClick={handleCancel}
              className="px-3 py-1.5 rounded-lg border bg-white text-red-600 border-red-200 hover:bg-red-50 dark:bg-black dark:text-red-500 dark:border-red-800 dark:hover:bg-red-900/30 text-xs font-semibold flex items-center gap-1"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Cancel</span>
            </button>
            <button
              onClick={() => onNavigate('/datasets')}
              className="px-3.5 py-1.5 rounded-lg bg-[#2D4351] text-white text-xs font-semibold hover:bg-[#20313C] flex items-center gap-1 shadow-sm"
            >
              <Database className="w-3.5 h-3.5" />
              <span>View Dataset</span>
            </button>
          </div>
        </div>

        {/* Telemetry Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-[#F8F9FA] rounded-xl border border-[#E5E7EB]">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Current Phase</span>
            <p className="text-sm font-bold text-gray-900 mt-0.5">{job.currentStep}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Records Extracted</span>
            <p className="text-sm font-bold text-green-700 font-mono mt-0.5">{job.recordsFound.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Duration</span>
            <p className="text-sm font-bold text-gray-900 font-mono mt-0.5">{job.duration}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Progress</span>
            <p className="text-sm font-bold text-[#2D4351] font-mono mt-0.5">{job.progress}%</p>
          </div>
        </div>

        {/* Live Logs */}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-2">
            Execution Log Stream
          </h3>
          <div className="bg-[#111827] rounded-xl p-4 text-xs font-mono text-gray-300 space-y-1.5 max-h-64 overflow-y-auto">
            {job.logs.map((log, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-gray-500 text-[11px]">[{log.timestamp}]</span>
                <span className="text-green-400">[{log.level.toUpperCase()}]</span>
                <span className="text-gray-200">{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
