import React from 'react';
import { LeadStatus } from '../../types';

interface StatusBadgeProps {
  status: LeadStatus | string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'sm' }) => {
  const getStyles = () => {
    switch (status) {
      case 'Interested':
      case 'Qualified':
      case 'Completed':
      case 'Active':
        return 'bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 font-semibold';
      case 'Not Interested':
      case 'Failed':
      case 'Delayed':
        return 'bg-white text-red-600 border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 font-semibold';
      case 'Running':
      case 'In Progress':
        return 'bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 animate-pulse font-semibold';
      default:
        // New, Called, Emailed, Follow Up, Queued, Pending, etc.
        return 'bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 font-semibold';
    }
  };

  const px = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center rounded-md border font-medium tracking-tight ${px} ${getStyles()}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          status === 'Interested' || status === 'Qualified' || status === 'Completed' || status === 'Active'
            ? 'bg-green-600 dark:bg-green-500'
            : status === 'Failed' || status === 'Delayed' || status === 'Not Interested'
            ? 'bg-red-600 dark:bg-red-500'
            : 'bg-blue-600 dark:bg-blue-500'
        }`}
      />
      {status}
    </span>
  );
};
