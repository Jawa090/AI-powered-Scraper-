import React from 'react';
import { MOCK_EMPLOYEES } from '../mock/employees';
import { useDataOps } from '../context/DataOpsContext';
import { ArrowLeft, Users2, PhoneCall, Mail, ThumbsUp, Clock, CheckCircle2 } from 'lucide-react';

interface EmployeeDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const EmployeeDetail: React.FC<EmployeeDetailProps> = ({ id, onNavigate }) => {
  const { leads, activities } = useDataOps();
  const employee = MOCK_EMPLOYEES.find(e => e.id === id) || MOCK_EMPLOYEES[0];
  const assignedLeads = leads.filter(l => l.assignedTo === employee.id || l.assignedToName === employee.name);
  const employeeActivities = activities.filter(a => a.user.toLowerCase().includes(employee.name.toLowerCase()));

  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/employees')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Employees</span>
      </button>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E5E7EB] pb-5 mb-5">
          <div className="flex items-center gap-3.5">
            <img
              src={employee.avatar}
              alt={employee.name}
              className="w-14 h-14 rounded-full object-cover ring-2 ring-gray-100"
            />
            <div>
              <h1 className="text-xl font-bold text-gray-900">{employee.name}</h1>
              <p className="text-xs text-[#848485]">
                {employee.role} • <span className="font-semibold text-gray-800">{employee.departmentName}</span> •{' '}
                <a href={`mailto:${employee.email}`} className="text-blue-600 hover:underline">{employee.email}</a>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
              {employee.status}
            </span>
          </div>
        </div>

        {/* 4 Performance Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-[#F8F9FA] rounded-xl border border-[#E5E7EB] mb-6">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Assigned Pipeline</span>
            <p className="text-xl font-bold text-gray-900 font-mono mt-0.5">{employee.assignedCount}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Outbound Calls</span>
            <p className="text-xl font-bold text-blue-700 font-mono mt-0.5">{employee.callsCount}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Emails Sent</span>
            <p className="text-xl font-bold text-purple-700 font-mono mt-0.5">{employee.emailsCount}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Interested Leads</span>
            <p className="text-xl font-bold text-emerald-600 font-mono mt-0.5">{employee.interestedCount}</p>
          </div>
        </div>

        {/* Assigned leads summary */}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-3">
            Assigned Leads in Workspace ({assignedLeads.length})
          </h3>
          <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
            {assignedLeads.slice(0, 4).map(l => (
              <div key={l.id} className="p-3 flex items-center justify-between text-xs hover:bg-gray-50">
                <div>
                  <span className="font-semibold text-gray-900">{l.name}</span>
                  <span className="text-gray-500 ml-2">{l.company}</span>
                </div>
                <button
                  onClick={() => onNavigate('/leads')}
                  className="text-blue-600 hover:underline text-[11px]"
                >
                  View Lead
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
