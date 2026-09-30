import React from 'react';
import { ArrowLeft } from 'lucide-react';

interface EmployeeDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const EmployeeDetail: React.FC<EmployeeDetailProps> = ({ id, onNavigate }) => {
  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/employees')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Employees</span>
      </button>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-12 text-center">
        <h2 className="text-sm font-semibold text-gray-900">No Employee Profile Found</h2>
        <p className="text-xs text-gray-500 mt-1">
          No employee record exists for ID "{id}".
        </p>
      </div>
    </div>
  );
};
