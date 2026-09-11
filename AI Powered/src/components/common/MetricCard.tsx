import React from 'react';
import { TrendingUp, TrendingDown, LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  subtext?: string;
  icon?: LucideIcon;
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  change,
  changeType = 'positive',
  subtext,
  icon: Icon,
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`bg-white border border-[#E5E7EB] rounded-lg p-4 transition-all duration-150 ${
        onClick ? 'cursor-pointer hover:border-[#2D4351] hover:shadow-subtle' : ''
      }`}
    >
      <div className="flex items-center justify-between text-xs font-medium text-[#848485] mb-2">
        <span>{title}</span>
        {Icon && <Icon className="w-4 h-4 text-[#848485]" />}
      </div>

      <div className="flex items-baseline justify-between">
        <span className="text-2xl font-bold tracking-tight text-[#111827]">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </span>

        {change && (
          <span
            className={`inline-flex items-center text-xs font-medium px-1.5 py-0.5 rounded ${
              changeType === 'positive'
                ? 'text-emerald-700 bg-emerald-50'
                : changeType === 'negative'
                ? 'text-rose-700 bg-rose-50'
                : 'text-gray-600 bg-gray-100'
            }`}
          >
            {changeType === 'positive' ? (
              <TrendingUp className="w-3 h-3 mr-1" />
            ) : changeType === 'negative' ? (
              <TrendingDown className="w-3 h-3 mr-1" />
            ) : null}
            {change}
          </span>
        )}
      </div>

      {subtext && <p className="text-xs text-[#848485] mt-1.5">{subtext}</p>}
    </div>
  );
};
