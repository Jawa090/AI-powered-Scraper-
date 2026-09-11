import React from 'react';
import { MOCK_CAMPAIGNS } from '../mock/campaigns';
import { StatusBadge } from '../components/common/StatusBadge';
import { ArrowLeft, Users2, Calendar, CheckCircle2, Clock, Megaphone } from 'lucide-react';

interface CampaignDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const CampaignDetail: React.FC<CampaignDetailProps> = ({ id, onNavigate }) => {
  const campaign = MOCK_CAMPAIGNS.find(c => c.id === id) || MOCK_CAMPAIGNS[0];

  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/campaigns')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Campaigns</span>
      </button>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E5E7EB] pb-5 mb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900">{campaign.name}</h1>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-xs text-[#848485] mt-1">
              Department: <span className="font-semibold text-gray-800">{campaign.departmentName}</span> • Owned by{' '}
              <span className="font-semibold text-gray-800">{campaign.owner}</span> • Schedule: {campaign.startDate} to {campaign.endDate}
            </p>
          </div>

          <button
            onClick={() => onNavigate('/leads')}
            className="px-4 py-2 text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-lg shadow-sm flex items-center gap-1.5"
          >
            <Users2 className="w-3.5 h-3.5" />
            <span>Work Leads in Workspace</span>
          </button>
        </div>

        {/* 4 Metric Columns */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-[#F8F9FA] rounded-xl border border-[#E5E7EB] mb-6">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Target Leads</span>
            <p className="text-xl font-bold text-gray-900 font-mono mt-0.5">{campaign.totalLeads.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Contacted Leads</span>
            <p className="text-xl font-bold text-blue-700 font-mono mt-0.5">{campaign.contactedCount.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Interested Pipeline</span>
            <p className="text-xl font-bold text-emerald-600 font-mono mt-0.5">{campaign.interestedCount}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Pending Rep Actions</span>
            <p className="text-xl font-bold text-amber-600 font-mono mt-0.5">{campaign.pendingCount}</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex justify-between text-xs font-semibold">
            <span>Campaign Execution Progress</span>
            <span>{campaign.progress}% Complete</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
            <div
              className="bg-[#2D4351] h-full rounded-full transition-all duration-300"
              style={{ width: `${campaign.progress}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
