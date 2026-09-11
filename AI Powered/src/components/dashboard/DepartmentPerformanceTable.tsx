import React from 'react';
import { Department } from '../../types';
import { Building2, ChevronRight, TrendingUp } from 'lucide-react';

interface DepartmentPerformanceTableProps {
  departments: Department[];
  onSelectDepartment?: (deptId: string) => void;
}

export const DepartmentPerformanceTable: React.FC<DepartmentPerformanceTableProps> = ({
  departments,
  onSelectDepartment,
}) => {
  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
      <div className="p-4 border-b border-[#E5E7EB] flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Department Performance</h3>
          <p className="text-xs text-[#848485]">Operational throughput across cross-functional teams</p>
        </div>
        <span className="text-xs font-semibold text-[#2D4351] bg-[#EAEFF2] px-2.5 py-1 rounded-md">
          {departments.length} Active Departments
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[#848485] font-semibold">
              <th className="py-2.5 px-4">Department</th>
              <th className="py-2.5 px-3 text-right">Total Leads</th>
              <th className="py-2.5 px-3 text-right">Assigned</th>
              <th className="py-2.5 px-3 text-right">Called</th>
              <th className="py-2.5 px-3 text-right">Emailed</th>
              <th className="py-2.5 px-3 text-right">Interested</th>
              <th className="py-2.5 px-3 text-right">Pending</th>
              <th className="py-2.5 px-4 text-right">Completion</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {departments.map(dept => (
              <tr
                key={dept.id}
                onClick={() => onSelectDepartment && onSelectDepartment(dept.id)}
                className="hover:bg-gray-50/80 cursor-pointer transition-colors"
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded bg-[#2D4351]/10 text-[#2D4351] flex items-center justify-center font-bold text-[10px]">
                      {dept.code}
                    </div>
                    <div>
                      <span className="font-semibold text-gray-900 block">{dept.name}</span>
                      <span className="text-[11px] text-gray-400">{dept.managerName}</span>
                    </div>
                  </div>
                </td>
                <td className="py-3 px-3 text-right font-medium text-gray-900">
                  {dept.leadsCount.toLocaleString()}
                </td>
                <td className="py-3 px-3 text-right text-gray-700">
                  {dept.assignedCount.toLocaleString()}
                </td>
                <td className="py-3 px-3 text-right text-blue-700 font-medium">
                  {dept.calledCount.toLocaleString()}
                </td>
                <td className="py-3 px-3 text-right text-purple-700 font-medium">
                  {dept.emailedCount.toLocaleString()}
                </td>
                <td className="py-3 px-3 text-right text-emerald-700 font-bold">
                  {dept.interestedCount.toLocaleString()}
                </td>
                <td className="py-3 px-3 text-right text-gray-500">
                  {dept.pendingCount.toLocaleString()}
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="bg-[#2D4351] h-full rounded-full transition-all duration-300"
                        style={{ width: `${Math.min(100, dept.completionRate)}%` }}
                      />
                    </div>
                    <span className="font-semibold text-gray-900 w-8 text-right">
                      {dept.completionRate}%
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
