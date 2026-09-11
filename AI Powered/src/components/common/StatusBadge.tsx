import React from 'react';
import { LeadStatus } from '../../types';

interface StatusBadgeProps {
  status: LeadStatus | string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'sm' }) => {
  const getStyles = () => {
    switch (status) {
      case 'New':
        return 'bg-gray-100 text-gray-700 border-gray-200';
      case 'Called':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'Emailed':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case 'Interested':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200 font-semibold';
      case 'Follow Up':
        return 'bg-amber-50 text-amber-700 border-amber-200 font-semibold';
      case 'Qualified':
        return 'bg-teal-50 text-teal-800 border-teal-200 font-semibold';
      case 'Not Interested':
        return 'bg-rose-50 text-rose-700 border-rose-200';
      case 'Completed':
      case 'Active':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'Running':
      case 'In Progress':
        return 'bg-sky-50 text-sky-700 border-sky-200 animate-pulse';
      case 'Queued':
      case 'Pending':
        return 'bg-gray-100 text-gray-600 border-gray-200';
      case 'Failed':
      case 'Delayed':
        return 'bg-red-50 text-red-700 border-red-200';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  const px = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center rounded-md border font-medium tracking-tight ${px} ${getStyles()}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          status === 'Interested' || status === 'Qualified' || status === 'Completed'
            ? 'bg-emerald-500'
            : status === 'Running' || status === 'Called'
            ? 'bg-blue-500'
            : status === 'Emailed'
            ? 'bg-purple-500'
            : status === 'Follow Up'
            ? 'bg-amber-500'
            : status === 'Failed'
            ? 'bg-red-500'
            : 'bg-gray-400'
        }`}
      />
      {status}
    </span>
  );
};
