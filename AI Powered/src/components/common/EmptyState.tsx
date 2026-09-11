import React from 'react';
import { LucideIcon, Database } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: LucideIcon;
  actionText?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon: Icon = Database,
  actionText,
  onAction,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center bg-white border border-dashed border-[#E5E7EB] rounded-xl my-4">
      <div className="w-12 h-12 rounded-full bg-[#EAEFF2] flex items-center justify-center text-[#2D4351] mb-4">
        <Icon className="w-6 h-6" />
      </div>
      <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
      <p className="text-xs text-[#848485] max-w-sm mt-1 mb-5">{description}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="inline-flex items-center px-3.5 py-1.5 rounded-md text-xs font-medium bg-[#2D4351] text-white hover:bg-[#20313C] transition-colors"
        >
          {actionText}
        </button>
      )}
    </div>
  );
};
