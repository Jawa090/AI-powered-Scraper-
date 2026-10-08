import React, { useState } from 'react';
import { UserCheck, Search, Filter } from 'lucide-react';
import { Employee } from '../types';

interface EmployeesProps {
  onNavigate: (path: string) => void;
}

const employees: Employee[] = [];

export const Employees: React.FC<EmployeesProps> = ({ onNavigate }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [deptFilter, setDeptFilter] = useState('all');

  const filteredEmployees = employees.filter(emp => {
    if (deptFilter !== 'all' && emp.departmentId !== deptFilter) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        emp.name.toLowerCase().includes(q) ||
        emp.role.toLowerCase().includes(q) ||
        emp.departmentName.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            Employee Productivity Directory
          </h1>
          <p className="text-xs text-[#848485] mt-0.5">
            Operational quotas, call pacing, and sequence throughput by individual representative
          </p>
        </div>
      </div>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-3.5 shadow-card flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Search employee by name or role..."
            className="w-full bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

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
      </div>

      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[#848485] font-semibold">
              <th className="py-2.5 px-4">Employee</th>
              <th className="py-2.5 px-3">Department</th>
              <th className="py-2.5 px-3 text-right">Assigned</th>
              <th className="py-2.5 px-3 text-right">Completed</th>
              <th className="py-2.5 px-3 text-right">Calls</th>
              <th className="py-2.5 px-3 text-right">Emails</th>
              <th className="py-2.5 px-3 text-right">Interested</th>
              <th className="py-2.5 px-3 text-right">Pending</th>
              <th className="py-2.5 px-4 text-right">Completion %</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filteredEmployees.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-12 text-center text-xs text-gray-400">
                  No employees found in directory.
                </td>
              </tr>
            ) : (
              filteredEmployees.map(emp => (
                <tr
                  key={emp.id}
                  onClick={() => onNavigate(`/employees/${emp.id}`)}
                  className="hover:bg-gray-50/80 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2.5">
                      <img src={emp.avatar} alt={emp.name} className="w-7 h-7 rounded-full object-cover ring-1 ring-gray-200" />
                      <div>
                        <span className="font-semibold text-gray-900 block">{emp.name}</span>
                        <span className="text-[11px] text-gray-400">{emp.role}</span>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-3 font-medium text-gray-700">{emp.departmentName}</td>
                  <td className="py-3 px-3 text-right font-mono text-gray-900">{emp.assignedCount}</td>
                  <td className="py-3 px-3 text-right font-mono text-gray-700">{emp.completedCount}</td>
                  <td className="py-3 px-3 text-right font-mono text-blue-700 font-medium">{emp.callsCount}</td>
                  <td className="py-3 px-3 text-right font-mono text-blue-700 font-medium">{emp.emailsCount}</td>
                  <td className="py-3 px-3 text-right font-mono text-green-700 font-bold">{emp.interestedCount}</td>
                  <td className="py-3 px-3 text-right font-mono text-gray-500">{emp.pendingCount}</td>
                  <td className="py-3 px-4 text-right">
                    <span className="font-mono font-bold text-gray-900">{emp.completionRate}%</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
