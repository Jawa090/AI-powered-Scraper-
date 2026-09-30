import React from 'react';
import { StatusBadge } from '../components/common/StatusBadge';
import { Megaphone, Calendar, Users2, ArrowRight, TrendingUp } from 'lucide-react';
import { Campaign } from '../types';

interface CampaignsProps {
  onNavigate: (path: string) => void;
}

const campaigns: Campaign[] = [];

export const Campaigns: React.FC<CampaignsProps> = ({ onNavigate }) => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            Outreach Campaigns
          </h1>
          <p className="text-xs text-[#848485] mt-0.5">
            Cross-departmental calling waves and automated email sequences
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {campaigns.length === 0 ? (
          <div className="col-span-full py-12 text-center text-xs text-gray-400 bg-white border border-[#E5E7EB] rounded-xl">
            No outreach campaigns currently active.
          </div>
        ) : (
          campaigns.map(camp => (
          <div
            key={camp.id}
            onClick={() => onNavigate(`/campaigns/${camp.id}`)}
            className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-card hover:border-[#2D4351] hover:shadow-dropdown transition-all cursor-pointer flex flex-col justify-between"
          >
            <div>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-gray-900">{camp.name}</h3>
                    <StatusBadge status={camp.status} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {camp.departmentName} • Owned by <span className="font-medium text-gray-700">{camp.owner}</span>
                  </p>
                </div>
                <span className="text-lg font-bold font-mono text-[#2D4351]">
                  {camp.progress}%
                </span>
              </div>

              <p className="text-xs text-[#848485] mt-3 leading-relaxed">
                {camp.description}
              </p>
            </div>

            <div className="mt-5 pt-4 border-t border-gray-100 space-y-3">
              {/* Progress bar */}
              <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-[#2D4351] h-full rounded-full transition-all duration-300"
                  style={{ width: `${camp.progress}%` }}
                />
              </div>

              <div className="flex items-center justify-between text-xs text-gray-600">
                <span className="font-semibold text-gray-900 font-mono">
                  {camp.totalLeads.toLocaleString()} Target Leads
                </span>
                <span className="text-emerald-700 font-semibold font-mono">
                  {camp.interestedCount} Interested
                </span>
                <span className="text-gray-400">
                  Ends {camp.endDate}
                </span>
              </div>
            </div>
          </div>
        )))}
      </div>
    </div>
  );
};
