import React from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { Building2, Bot, Users2, ArrowRight } from 'lucide-react';

interface DepartmentsProps {
  onNavigate: (path: string) => void;
}

export const Departments: React.FC<DepartmentsProps> = ({ onNavigate }) => {
  const { departments } = useDataOps();

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            Operating Departments
          </h1>
          <p className="text-xs text-[#848485] mt-0.5">
            Decentralized business units paired with specialized autonomous intelligence agents
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {departments.map(dept => (
          <div
            key={dept.id}
            onClick={() => onNavigate(`/departments/${dept.id}`)}
            className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-card hover:border-[#2D4351] hover:shadow-dropdown transition-all cursor-pointer flex flex-col justify-between group"
          >
            <div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-[#2D4351] text-white flex items-center justify-center font-bold text-xs shadow-sm">
                    {dept.code}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-gray-900 group-hover:text-[#2D4351] transition-colors">
                      {dept.name}
                    </h3>
                    <p className="text-[11px] text-[#848485]">Lead: {dept.managerName}</p>
                  </div>
                </div>

                <span className="text-sm font-mono font-bold text-gray-900">
                  {dept.completionRate}%
                </span>
              </div>

              <p className="text-xs text-gray-600 mt-3 leading-relaxed">
                {dept.description}
              </p>
            </div>

            <div className="mt-5 pt-4 border-t border-gray-100 space-y-3">
              <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-[#2D4351] h-full rounded-full transition-all duration-300"
                  style={{ width: `${dept.completionRate}%` }}
                />
              </div>

              <div className="flex items-center justify-between text-xs text-gray-600">
                <span>
                  <strong className="text-gray-900 font-mono">{dept.leadsCount.toLocaleString()}</strong> leads
                </span>
                <span>
                  <strong className="text-blue-700 font-mono">{dept.calledCount.toLocaleString()}</strong> calls
                </span>
                <span>
                  <strong className="text-purple-700 font-mono">{dept.emailedCount.toLocaleString()}</strong> emails
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
