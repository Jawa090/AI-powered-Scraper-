import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api.service';
import type { Job } from '../types';
import { useDataOps } from '../context/DataOpsContext';
import { DataGenerationStepper } from '../components/data-requests/DataGenerationStepper';
import { ArrowLeft } from 'lucide-react';

interface DataRequestDetailProps {
  id: string;
  onNavigate: (path: string) => void;
}

export const DataRequestDetail: React.FC<DataRequestDetailProps> = ({
  id,
  onNavigate,
}) => {
  const { getLiveJob } = useDataOps();
  const [fetched, setFetched] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);
  const known = getLiveJob(id);

  // Not in memory (page refresh, direct link, or a job started elsewhere):
  // load it from the backend and keep polling while it runs.
  useEffect(() => {
    if (known) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      setLoading(true);
      const j = await apiService.getJob(id);
      if (cancelled) return;
      setLoading(false);
      setFetched(j);
      if (j && (j.status === 'Running' || j.status === 'Queued')) {
        timer = setTimeout(load, 2000);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id, known]);

  const job = known || fetched;

  if (!job && loading) {
    return (
      <div className="p-8 text-center">
        <p className="text-xs text-gray-500">Loading pipeline job…</p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="p-8 text-center">
        <p className="text-xs text-gray-500">Pipeline job not found.</p>
        <button
          onClick={() => onNavigate('/data-requests')}
          className="mt-3 text-xs text-blue-600 hover:underline"
        >
          Return to Data Requests
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <button
        onClick={() => onNavigate('/data-requests')}
        className="inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 font-medium transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Data Requests</span>
      </button>

      <DataGenerationStepper
        job={job}
        onViewLeads={() => onNavigate('/leads')}
        onViewDataset={() => onNavigate('/datasets')}
      />
    </div>
  );
};
