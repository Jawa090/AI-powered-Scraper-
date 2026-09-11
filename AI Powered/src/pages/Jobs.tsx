import React from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { StatusBadge } from '../components/common/StatusBadge';
import { ActivitySquare, Clock, ArrowRight } from 'lucide-react';

interface JobsProps {
  onNavigate: (path: string) => void;
}

export const Jobs: React.FC<JobsProps> = ({ onNavigate }) => {
  const { jobs } = useDataOps();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-gray-900">
              Background Job Infrastructure
            </h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
              Admin Only
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-0.5">
            Distributed worker cluster telemetry and async task orchestrations
          </p>
        </div>
      </div>

      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[#848485] font-semibold">
              <th className="py-2.5 px-4">Job ID & Name</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3">Department</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Started</th>
              <th className="py-2.5 px-3">Duration</th>
              <th className="py-2.5 px-4 text-right">Progress</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {jobs.map(job => (
              <tr
                key={job.id}
                onClick={() => onNavigate(`/jobs/${job.id}`)}
                className="hover:bg-gray-50/80 cursor-pointer transition-colors"
              >
                <td className="py-3 px-4">
                  <span className="font-semibold text-gray-900 block">{job.name}</span>
                  <span className="font-mono text-[11px] text-gray-400">{job.id}</span>
                </td>
                <td className="py-3 px-3 text-gray-600">{job.type}</td>
                <td className="py-3 px-3 text-gray-900 font-medium">{job.departmentName}</td>
                <td className="py-3 px-3">
                  <StatusBadge status={job.status} />
                </td>
                <td className="py-3 px-3 text-gray-500 whitespace-nowrap">{job.startedAt}</td>
                <td className="py-3 px-3 font-mono text-gray-700">{job.duration}</td>
                <td className="py-3 px-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          job.status === 'Completed' ? 'bg-emerald-500' : 'bg-[#2D4351]'
                        }`}
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                    <span className="font-mono font-semibold text-gray-900 w-8 text-right">
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
