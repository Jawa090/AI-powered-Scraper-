import React from 'react';
import { ArrowLeft } from 'lucide-react';

interface CampaignDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const CampaignDetail: React.FC<CampaignDetailProps> = ({ id, onNavigate }) => {
  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/campaigns')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Campaigns</span>
      </button>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-12 text-center">
        <h2 className="text-sm font-semibold text-gray-900">No Campaign Found</h2>
        <p className="text-xs text-gray-500 mt-1">
          No outreach campaign exists for ID "{id}".
        </p>
      </div>
    </div>
  );
};
