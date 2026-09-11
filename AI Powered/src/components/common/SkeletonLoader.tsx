import React from 'react';

export const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => {
  return (
    <div className="w-full animate-pulse space-y-3">
      <div className="h-9 bg-gray-100 rounded-md w-full" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 py-2 border-b border-gray-100">
          <div className="h-4 bg-gray-100 rounded w-6" />
          <div className="h-4 bg-gray-100 rounded w-1/4" />
          <div className="h-4 bg-gray-100 rounded w-1/6" />
          <div className="h-4 bg-gray-100 rounded w-1/5" />
          <div className="h-4 bg-gray-100 rounded w-1/6" />
          <div className="h-4 bg-gray-100 rounded w-12 ml-auto" />
        </div>
      ))}
    </div>
  );
};

export const CardSkeleton: React.FC = () => {
  return (
    <div className="bg-white border border-[#E5E7EB] rounded-lg p-4 animate-pulse space-y-3">
      <div className="flex justify-between">
        <div className="h-3.5 bg-gray-100 rounded w-24" />
        <div className="h-4 bg-gray-100 rounded w-4" />
      </div>
      <div className="h-7 bg-gray-100 rounded w-32" />
      <div className="h-3 bg-gray-100 rounded w-40" />
    </div>
  );
};
