import React, { useState, useEffect } from 'react';
import { Code2, Play, CheckCircle2, Loader2, Sparkles, Sliders, ExternalLink, Terminal } from 'lucide-react';
import { StatusBadge } from '../components/common/StatusBadge';
import { apiService } from '../services/api.service';
import { useDataOps } from '../context/DataOpsContext';

interface ScriptsProps {
  onNavigate?: (path: string) => void;
}

export const Scripts: React.FC<ScriptsProps> = ({ onNavigate }) => {
  const { showToast } = useDataOps();
  const [scripts, setScripts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState(false);

  // Run modal state
  const [selectedScript, setSelectedScript] = useState<any | null>(null);
  const [limit, setLimit] = useState<number>(20);
  const [keyword, setKeyword] = useState<string>('contractor');
  const [location, setLocation] = useState<string>('new-york');
  const [running, setRunning] = useState(false);

  useEffect(() => {
    loadScripts();
  }, []);

  const loadScripts = async () => {
    setLoading(true);
    try {
      const isHealthy = await apiService.getHealth();
      setBackendOnline(isHealthy);
      if (isHealthy) {
        const live = await apiService.getScripts();
        if (live && live.length > 0) {
          setScripts(live);
          setLoading(false);
          return;
        }
      }
    } catch (e) {
      console.warn('Backend unavailable:', e);
    }
    setScripts([]);
    setLoading(false);
  };

  const handleOpenRunModal = (script: any) => {
    setSelectedScript(script);
    setLimit(script.defaultLimit || 20);
    setKeyword('contractor');
    setLocation('new-york');
  };

  const handleExecute = async () => {
    if (!selectedScript) return;
    setRunning(true);
    try {
      const params: Record<string, any> = { limit: Number(limit) };
      if (selectedScript.id === 'jwiz') {
        params.keyword = keyword;
        params.location = location;
      }
      const res = await apiService.runScript(selectedScript.id, params);
      showToast('Scraper Launched', `Job ${res.jobId} started for ${selectedScript.name}.`, 'success');
      setSelectedScript(null);
      if (onNavigate) {
        onNavigate(`/data-requests/${res.jobId}`);
      }
    } catch (err: any) {
      showToast('Execution Error', err.message || 'Failed to launch scraper script.', 'error');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-gray-900">
              Data Collection Script Registry
            </h1>
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded border ${
                backendOnline
                  ? 'bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800'
                  : 'bg-white text-red-600 border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800'
              }`}
            >
              {backendOnline ? 'FastAPI Connected (Port 8000)' : 'Offline / Standalone'}
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-0.5">
            4 Production Scraping Engines: Dallas Bonfire, DASNY, JWiz Directory, and NYSCR Contracts
          </p>
        </div>

        <button
          onClick={loadScripts}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
        >
          Refresh Status
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {scripts.map(script => (
          <div
            key={script.id}
            className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-card space-y-4 hover:border-gray-300 transition-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-gray-900">{script.name}</h3>
                  <span className="font-mono text-[11px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                    {script.version || 'v1.0'}
                  </span>
                </div>
                {script.file && (
                  <div className="flex items-center gap-1.5 text-[11px] font-mono text-blue-600">
                    <Terminal className="w-3 h-3" />
                    <span>Backend/{script.file}</span>
                  </div>
                )}
                <p className="text-xs text-[#848485] leading-relaxed">
                  {script.description}
                </p>
              </div>
              <StatusBadge status={script.status || 'Active'} />
            </div>

            {/* Capabilities */}
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485] block mb-1.5">
                Engine Capabilities
              </span>
              <div className="flex flex-wrap gap-1.5">
                {(script.capabilities || []).map((c: string) => (
                  <span
                    key={c}
                    className="text-[11px] px-2 py-0.5 rounded-md bg-[#F8F9FA] border border-[#E5E7EB] text-gray-700 font-medium"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>

            {/* Footer Stats & Run Action */}
            <div className="pt-3 border-t border-gray-100 flex items-center justify-between text-xs">
              <div className="text-gray-500 flex items-center gap-3">
                {script.category && (
                  <span className="text-[11px] font-medium text-gray-600 bg-gray-50 px-2 py-0.5 rounded border border-gray-100">
                    {script.category}
                  </span>
                )}
                <span className="font-mono">
                  Success: <strong className="text-green-700">{script.successRate || '99%'}</strong>
                </span>
              </div>

              <span className="text-[10px] text-gray-500 font-medium bg-gray-100 px-2 py-1 rounded">
                Agent Managed
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Execution Modal */}
      {selectedScript && (
        <div className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-2xl max-w-md w-full p-6 space-y-5">
            <div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-white text-blue-600 border border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 flex items-center justify-center">
                  <Play className="w-4 h-4 fill-current" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-gray-900">
                    Execute {selectedScript.name}
                  </h2>
                  <p className="text-xs text-gray-500">
                    Target Script: <code className="text-blue-600 font-mono">{selectedScript.file || selectedScript.id}</code>
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-gray-700 mb-1">
                  Target Record Limit
                </label>
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={limit}
                  onChange={e => setLimit(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                />
                <span className="text-[11px] text-gray-400 mt-0.5 block">
                  Recommended test run: 10 - 25 records
                </span>
              </div>

              {selectedScript.id === 'jwiz' && (
                <>
                  <div>
                    <label className="block font-semibold text-gray-700 mb-1">
                      Business Keyword
                    </label>
                    <input
                      type="text"
                      value={keyword}
                      onChange={e => setKeyword(e.target.value)}
                      placeholder="e.g. contractor, plumber, electrician"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-gray-700 mb-1">
                      Location Slug
                    </label>
                    <input
                      type="text"
                      value={location}
                      onChange={e => setLocation(e.target.value)}
                      placeholder="e.g. new-york, brooklyn, lakewood"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  </div>
                </>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-gray-100">
              <button
                type="button"
                onClick={() => setSelectedScript(null)}
                disabled={running}
                className="px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecute}
                disabled={running}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors shadow-sm disabled:opacity-50"
              >
                {running ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Launching Engine...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    Start Extraction Pipeline
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
