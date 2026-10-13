import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api.service';
import { SystemStatus } from '../../types';
import { Database, Server, Activity, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';

export const SystemHealthBadge: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus>({
    backend: false,
    database: false,
    api: false,
    timestamp: Date.now(),
    registeredScripts: 4,
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [isOpen, setIsOpen] = useState<boolean>(false);

  const fetchStatus = async () => {
    setLoading(true);
    const s = await apiService.getSystemStatus();
    setStatus(s);
    setLoading(false);
  };

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, 15000);
    return () => clearInterval(timer);
  }, []);

  const isAllHealthy = status.backend && status.database;

  return (
    <div className="relative inline-block text-left">
      {/* Clickable Badge */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        title="Live Backend & Database Health Status"
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all ${
          isAllHealthy
            ? 'bg-white text-green-600 border-green-200 hover:bg-green-50 dark:bg-black dark:text-green-500 dark:border-green-800'
            : status.backend
            ? 'bg-white text-blue-600 border-blue-200 hover:bg-blue-50 dark:bg-black dark:text-blue-500 dark:border-blue-800'
            : 'bg-white text-red-600 border-red-200 hover:bg-red-50 dark:bg-black dark:text-red-500 dark:border-red-800'
        }`}
      >
        <span className="relative flex h-2 w-2">
          {isAllHealthy && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          )}
          <span
            className={`relative inline-flex rounded-full h-2 w-2 ${
              isAllHealthy ? 'bg-green-600 dark:bg-green-500' : status.backend ? 'bg-blue-600 dark:bg-blue-500' : 'bg-red-600 dark:bg-red-500'
            }`}
          ></span>
        </span>
        <span className="font-semibold">{isAllHealthy ? 'Backend: Healthy' : status.backend ? 'DB Issue' : 'Offline'}</span>
      </button>

      {/* Popover Dropdown */}
      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-72 rounded-xl bg-white border border-gray-200 shadow-xl z-50 p-3.5 space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-gray-100">
              <div className="flex items-center gap-1.5 text-xs font-bold text-gray-900">
                <Activity className="w-4 h-4 text-blue-600" />
                <span>System Infrastructure Status</span>
              </div>
              <button
                onClick={fetchStatus}
                disabled={loading}
                className="text-gray-400 hover:text-gray-600 p-1 rounded hover:bg-gray-100 transition-colors"
                title="Refresh Status"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-600' : ''}`} />
              </button>
            </div>

            <div className="space-y-2">
              {/* Backend Process */}
              <div className="flex items-center justify-between text-xs p-2 rounded-lg bg-gray-50">
                <div className="flex items-center gap-2 text-gray-700">
                  <Server className="w-4 h-4 text-gray-500" />
                  <span>FastAPI Process</span>
                </div>
                <div className="flex items-center gap-1">
                  {status.backend ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 px-2 py-0.5 rounded border">
                      <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-500" />
                      Healthy
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-white text-red-600 border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 px-2 py-0.5 rounded border">
                      <AlertCircle className="w-3 h-3 text-red-600 dark:text-red-500" />
                      Offline
                    </span>
                  )}
                </div>
              </div>

              {/* PostgreSQL DB */}
              <div className="flex items-center justify-between text-xs p-2 rounded-lg bg-gray-50">
                <div className="flex items-center gap-2 text-gray-700">
                  <Database className="w-4 h-4 text-gray-500" />
                  <span>PostgreSQL Database</span>
                </div>
                <div className="flex items-center gap-1">
                  {status.database ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 px-2 py-0.5 rounded border">
                      <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-500" />
                      Connected
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-white text-red-600 border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 px-2 py-0.5 rounded border">
                      <AlertCircle className="w-3 h-3 text-red-600 dark:text-red-500" />
                      Disconnected
                    </span>
                  )}
                </div>
              </div>

              {/* Scrapers Status */}
              <div className="flex items-center justify-between text-xs p-2 rounded-lg bg-gray-50">
                <div className="flex items-center gap-2 text-gray-700">
                  <Activity className="w-4 h-4 text-gray-500" />
                  <span>Scraper Engines</span>
                </div>
                <span className="text-[11px] font-semibold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 px-2 py-0.5 rounded border">
                  {status.registeredScripts} Active (L4)
                </span>
              </div>
            </div>

            <div className="pt-1 text-[10px] text-gray-400 text-right">
              Probed: {new Date(status.timestamp).toLocaleTimeString()}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
