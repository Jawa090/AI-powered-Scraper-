import React from 'react';
import { Activity } from '../../types';
import { Phone, Mail, Sparkles, UserPlus, Clock, ArrowRight } from 'lucide-react';

interface RecentActivityListProps {
  activities: Activity[];
  onSelectActivity?: (activity: Activity) => void;
}

export const RecentActivityList: React.FC<RecentActivityListProps> = ({
  activities,
  onSelectActivity,
}) => {
  const getIcon = (type: Activity['type']) => {
    switch (type) {
      case 'call':
        return <Phone className="w-3.5 h-3.5 text-blue-600" />;
      case 'email':
      case 'bulk_email':
        return <Mail className="w-3.5 h-3.5 text-blue-600" />;
      case 'generation':
        return <Sparkles className="w-3.5 h-3.5 text-green-600" />;
      case 'assignment':
        return <UserPlus className="w-3.5 h-3.5 text-blue-600" />;
      default:
        return <Clock className="w-3.5 h-3.5 text-gray-500" />;
    }
  };

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card h-full flex flex-col">
      <div className="flex items-center justify-between border-b border-[#E5E7EB] pb-3 mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Recent Activity</h3>
          <p className="text-xs text-[#848485]">Live stream of team and AI actions</p>
        </div>
        <span className="text-[10px] font-semibold bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 px-2 py-0.5 rounded border">
          Live Sync
        </span>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-gray-50 pr-1">
        {activities.slice(0, 7).map(act => (
          <div
            key={act.id}
            onClick={() => onSelectActivity && onSelectActivity(act)}
            className="py-2.5 px-2 hover:bg-gray-50 rounded-lg cursor-pointer transition-colors flex items-start gap-3 group"
          >
            <div className="w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0 mt-0.5 group-hover:bg-white group-hover:shadow-sm transition-all">
              {getIcon(act.type)}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-baseline justify-between gap-1">
                <span className="text-xs font-semibold text-gray-900 truncate">
                  {act.title}
                </span>
                <span className="text-[10px] text-gray-400 whitespace-nowrap">
                  {act.timestamp}
                </span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5 leading-snug line-clamp-2">
                {act.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
