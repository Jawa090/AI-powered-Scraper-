import React, { useState, useMemo } from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { StatusBadge } from '../components/common/StatusBadge';
import { Database, Search, Filter, Eye, Sparkles, Users2, Calendar } from 'lucide-react';
import { Dataset } from '../types';

interface DatasetsProps {
  onNavigate: (path: string) => void;
}

export const Datasets: React.FC<DatasetsProps> = ({ onNavigate }) => {
  const { datasets } = useDataOps();
  const [searchTerm, setSearchTerm] = useState('');
  const [deptFilter, setDeptFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const filteredDatasets = useMemo(() => {
    return datasets.filter(d => {
      if (deptFilter !== 'all' && d.departmentId !== deptFilter) return false;
      if (statusFilter !== 'all' && d.status !== statusFilter) return false;
      if (searchTerm) {
        const q = searchTerm.toLowerCase();
        return (
          d.name.toLowerCase().includes(q) ||
          d.departmentName.toLowerCase().includes(q) ||
          d.createdByName.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [datasets, deptFilter, statusFilter, searchTerm]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            Generated Intelligence Datasets
          </h1>
          <p className="text-xs text-[#848485] mt-0.5">
            Structured business databases produced by departmental AI agents
          </p>
        </div>

        <button
          onClick={() => onNavigate('/agent')}
          className="px-3.5 py-2 rounded-lg bg-[#2D4351] text-white hover:bg-[#20313C] text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5 text-green-400" />
          <span>Generate New Dataset</span>
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-3.5 shadow-card flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Search datasets by name or creator..."
            className="w-full bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            value={deptFilter}
            onChange={e => setDeptFilter(e.target.value)}
            className="text-xs bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-gray-700 focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          >
            <option value="all">All Departments</option>
            <option value="dept-sales-1">Sales 1</option>
            <option value="dept-sales-2">Sales 2</option>
            <option value="dept-email-mktg">Email Marketing</option>
            <option value="dept-biz-dev">Business Development</option>
            <option value="dept-research">Research</option>
          </select>

          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="text-xs bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg px-2.5 py-1.5 text-gray-700 focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          >
            <option value="all">All Statuses</option>
            <option value="Completed">Completed</option>
            <option value="Running">Running</option>
            <option value="Queued">Queued</option>
          </select>
        </div>
      </div>

      {/* Dataset Table */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[#848485] font-semibold">
              <th className="py-2.5 px-4">Dataset Name</th>
              <th className="py-2.5 px-3">Department</th>
              <th className="py-2.5 px-3">Created By</th>
              <th className="py-2.5 px-3 text-right">Total Records</th>
              <th className="py-2.5 px-3 text-right">Verified</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Created</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filteredDatasets.map(ds => (
              <tr
                key={ds.id}
                onClick={() => onNavigate(`/datasets/${ds.id}`)}
                className="hover:bg-gray-50/80 cursor-pointer transition-colors"
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-lg bg-[#2D4351]/10 text-[#2D4351] flex items-center justify-center flex-shrink-0">
                      <Database className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-gray-900 block">{ds.name}</span>
                      <span className="text-[11px] text-gray-400">{ds.tags.join(' • ')}</span>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 text-gray-700 font-medium">{ds.departmentName}</td>
                <td className="py-3 px-3 text-gray-600">{ds.createdByName}</td>
                <td className="py-3 px-3 text-right font-mono font-semibold text-gray-900">
                  {ds.recordsCount.toLocaleString()}
                </td>
                <td className="py-3 px-3 text-right font-mono text-green-600 font-semibold">
                  {ds.verifiedCount.toLocaleString()}
                </td>
                <td className="py-3 px-3">
                  <StatusBadge status={ds.status} />
                </td>
                <td className="py-3 px-3 text-gray-500 whitespace-nowrap">{ds.createdAt}</td>
                <td className="py-3 px-4 text-right" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => onNavigate('/leads')}
                    className="px-2.5 py-1 text-[11px] font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-md transition-colors shadow-sm inline-flex items-center gap-1"
                  >
                    <Users2 className="w-3 h-3" />
                    View Leads
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
