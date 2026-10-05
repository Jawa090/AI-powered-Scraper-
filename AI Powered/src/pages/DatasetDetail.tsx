import React from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { StatusBadge } from '../components/common/StatusBadge';
import { ArrowLeft, Users2, Database, ShieldCheck, CheckCircle2, FileText } from 'lucide-react';

interface DatasetDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const DatasetDetail: React.FC<DatasetDetailProps> = ({ id, onNavigate }) => {
  const { datasets, leads } = useDataOps();
  const dataset = datasets.find(d => d.id === id) || datasets[0];
  const datasetLeads = leads.filter(l => l.datasetId === dataset?.id);

  if (!dataset) {
    return <div className="p-8 text-center text-xs text-gray-500">Dataset not found</div>;
  }

  return (
    <div className="space-y-6">
      <button
        onClick={() => onNavigate('/datasets')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Datasets</span>
      </button>

      <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#E5E7EB] pb-5 mb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900">{dataset.name}</h1>
              <StatusBadge status={dataset.status} />
            </div>
            <p className="text-xs text-[#848485] mt-1">
              Created by <span className="font-semibold text-gray-800">{dataset.createdByName}</span> for{' '}
              <span className="font-semibold text-gray-800">{dataset.departmentName}</span> on {dataset.createdAt}
            </p>
          </div>

          <button
            onClick={() => onNavigate('/leads')}
            className="px-4 py-2 text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-lg shadow-sm flex items-center gap-1.5"
          >
            <Users2 className="w-3.5 h-3.5" />
            <span>Open Leads in Workspace</span>
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-[#F8F9FA] rounded-xl border border-[#E5E7EB]">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Total Records</span>
            <p className="text-xl font-bold text-gray-900 font-mono mt-0.5">{dataset.recordsCount.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Verified Contacts</span>
            <p className="text-xl font-bold text-emerald-600 font-mono mt-0.5">{dataset.verifiedCount.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Deduplicated</span>
            <p className="text-xl font-bold text-amber-600 font-mono mt-0.5">{dataset.duplicatesCount}</p>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485]">Associated Workflow</span>
            <p className="text-xs font-semibold text-gray-900 mt-1 truncate">{dataset.workflowName}</p>
          </div>
        </div>

        <div className="mt-6">
          <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-3">
            Sample Ingested Records ({datasetLeads.length} sample preview)
          </h3>
          <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
            {datasetLeads.slice(0, 5).map(lead => (
              <div key={lead.id} className="p-3 flex items-center justify-between hover:bg-gray-50 text-xs">
                <div>
                  <span className="font-semibold text-gray-900">{lead.name || lead.company || '—'}</span>
                  <span className="text-gray-500 ml-2">{lead.title ? `${lead.title} at ` : ''}{lead.company || '—'}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-gray-500 text-[11px]">{lead.email || '—'}</span>
                  <StatusBadge status={lead.status || 'New'} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
