import React from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { Sparkles, ArrowRight, Play, CheckCircle2, Clock, Activity } from 'lucide-react';
import { StatusBadge } from '../components/common/StatusBadge';

interface DataRequestsProps {
  onNavigate: (path: string) => void;
}

export const DataRequests: React.FC<DataRequestsProps> = ({ onNavigate }) => {
  const { jobs } = useDataOps();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            Data Collection Requests & Pipelines
          </h1>
          <p className="text-xs text-[#848485] mt-0.5">
            Monitor automated intelligence gathering, scraping jobs, and enrichment runs
          </p>
        </div>

        <button
          onClick={() => onNavigate('/agent')}
          className="px-3.5 py-2 rounded-lg bg-[#2D4351] text-white hover:bg-[#20313C] text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
          <span>New AI Data Request</span>
        </button>
      </div>

      {/* Requests Table */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[#848485] font-semibold">
              <th className="py-2.5 px-4">Request / Pipeline</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3">Department</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Current Phase</th>
              <th className="py-2.5 px-3 text-right">Target Volume</th>
              <th className="py-2.5 px-4 text-right">Progress</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {jobs.map(job => (
              <tr
                key={job.id}
                onClick={() => onNavigate(`/data-requests/${job.id}`)}
                className="hover:bg-gray-50/80 cursor-pointer transition-colors"
              >
                <td className="py-3 px-4">
                  <span className="font-semibold text-gray-900 block">{job.name}</span>
                  <span className="text-[11px] font-mono text-gray-400">{job.id}</span>
                </td>
                <td className="py-3 px-3 text-gray-600">{job.type}</td>
                <td className="py-3 px-3 text-gray-900 font-medium">{job.departmentName}</td>
                <td className="py-3 px-3">
                  <StatusBadge status={job.status} />
                </td>
                <td className="py-3 px-3 text-gray-700 font-medium">{job.currentStep}</td>
                <td className="py-3 px-3 text-right font-mono text-gray-900">
                  {job.totalTarget.toLocaleString()}
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          job.status === 'Completed' ? 'bg-emerald-500' : 'bg-[#2D4351]'
                        }`}
                        style={{ width: `${Math.min(100, job.progress)}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs font-semibold text-gray-900 w-9 text-right">
                      {job.progress}%
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
