import React from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { SYSTEM_AGENTS } from '../services/agent.service';
import { Employee, Campaign } from '../types';
import { ArrowLeft, Bot, Users2, Database, Megaphone, Sparkles, CheckCircle2 } from 'lucide-react';

interface DepartmentDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const DepartmentDetail: React.FC<DepartmentDetailProps> = ({ id, onNavigate }) => {
  const { departments, datasets, leads } = useDataOps();
  const dept = departments.find(d => d.id === id) || departments[0];

  const agent = SYSTEM_AGENTS.find(a => a.departmentId === dept?.id);
  const deptEmployees: Employee[] = [];
  const deptDatasets = datasets.filter(d => d.departmentId === dept?.id);
  const deptCampaigns: Campaign[] = [];

  if (!dept) return <div className="p-8 text-center text-xs text-gray-500">Department not found</div>;

  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/departments')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Departments</span>
      </button>

      {/* Header card */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E5E7EB] pb-5 mb-5">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-[#2D4351] text-white flex items-center justify-center font-bold text-base shadow-sm">
              {dept.code}
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">{dept.name}</h1>
              <p className="text-xs text-[#848485]">
                Operations Director: <span className="font-semibold text-gray-800">{dept.managerName}</span> • {dept.description}
              </p>
            </div>
          </div>

          <button
            onClick={() => onNavigate('/agent')}
            className="px-4 py-2 text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-lg shadow-sm flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5 text-green-400" />
            <span>Launch {dept.name} AI Agent</span>
          </button>
        </div>

        {/* 4 KPIs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-[#F8F9FA] rounded-xl border border-[#E5E7EB]">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Total Leads</span>
            <p className="text-xl font-bold text-gray-900 font-mono mt-0.5">{dept.leadsCount.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Calls Logged</span>
            <p className="text-xl font-bold text-blue-700 font-mono mt-0.5">{dept.calledCount.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Emails Dispatched</span>
            <p className="text-xl font-bold text-blue-700 font-mono mt-0.5">{dept.emailedCount.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Interested Leads</span>
            <p className="text-xl font-bold text-green-600 font-mono mt-0.5">{dept.interestedCount.toLocaleString()}</p>
          </div>
        </div>
      </div>

      {/* Agent & Team Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Dedicated AI Agent */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-card">
          <div className="flex items-center justify-between border-b border-[#E5E7EB] pb-3 mb-4">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-green-600" />
              <h3 className="text-sm font-semibold text-gray-900">Dedicated AI Agent</h3>
            </div>
            <span className="text-[10px] font-semibold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 px-2 py-0.5 rounded border">
              Active Neural v4.2
            </span>
          </div>

          {agent ? (
            <div className="space-y-3">
              <div>
                <span className="text-xs font-bold text-gray-900">{agent.name}</span>
                <p className="text-xs text-[#848485] mt-1 leading-relaxed">{agent.description}</p>
              </div>

              <div>
                <span className="text-[11px] font-semibold text-gray-700 block mb-1.5">
                  Autonomous Extraction Capabilities:
                </span>
                <div className="space-y-1">
                  {agent.capabilities.map(cap => (
                    <div key={cap} className="flex items-center gap-2 text-xs text-gray-700">
                      <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" />
                      <span>{cap}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-400">Standard agent attached.</p>
          )}
        </div>

        {/* Assigned Reps */}
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-card">
          <div className="flex items-center justify-between border-b border-[#E5E7EB] pb-3 mb-4">
            <div className="flex items-center gap-2">
              <Users2 className="w-4 h-4 text-[#2D4351]" />
              <h3 className="text-sm font-semibold text-gray-900">Department Team</h3>
            </div>
            <span className="text-xs font-mono font-medium text-gray-500">
              {deptEmployees.length} Members
            </span>
          </div>

          <div className="divide-y divide-gray-100">
            {deptEmployees.map(emp => (
              <div key={emp.id} className="py-2.5 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2.5">
                  <img src={emp.avatar} alt={emp.name} className="w-8 h-8 rounded-full object-cover" />
                  <div>
                    <span className="font-semibold text-gray-900 block">{emp.name}</span>
                    <span className="text-[11px] text-gray-500">{emp.role}</span>
                  </div>
                </div>
                <span className="font-mono text-gray-700 font-semibold">{emp.completionRate}% completion</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
