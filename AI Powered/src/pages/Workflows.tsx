import React from 'react';
import { GitBranch, ArrowDown, ArrowRight, CheckCircle2, Loader2, Play } from 'lucide-react';
import { StatusBadge } from '../components/common/StatusBadge';
import { Workflow } from '../types';

const workflows: Workflow[] = [];

export const Workflows: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-gray-900">
              Autonomous Extraction Workflows
            </h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 border">
              Admin Only
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-0.5">
            Visual execution graphs orchestrating scrapers, mailbox checkers, and deduplicators
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {workflows.length === 0 ? (
          <div className="py-12 text-center text-xs text-gray-400 bg-white border border-[#E5E7EB] rounded-xl">
            No autonomous extraction workflows configured.
          </div>
        ) : (
          workflows.map(wf => (
          <div
            key={wf.id}
            className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-6"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#E5E7EB] pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-gray-900">{wf.name}</h3>
                  <StatusBadge status={wf.status} />
                </div>
                <p className="text-xs text-[#848485] mt-1">{wf.description}</p>
              </div>
              <span className="text-xs text-gray-500 font-mono">Last executed: {wf.lastUsed}</span>
            </div>

            {/* Visual Node Pipeline */}
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485] block mb-3">
                Pipeline Stages & Node Dependency Graph:
              </span>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
                {wf.steps.map((step, idx) => {
                  const isDone = step.status === 'completed';
                  const isRunning = step.status === 'running';

                  return (
                    <div key={step.id} className="relative">
                      <div
                        className={`p-3 rounded-lg border flex flex-col justify-between h-24 ${
                          isDone
                            ? 'bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800'
                            : isRunning
                            ? 'bg-[#EAEFF2] border-[#2D4351] text-[#2D4351] ring-1 ring-[#2D4351]'
                            : 'bg-[#F8F9FA] border-gray-200 text-gray-500'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[10px] font-bold">Node 0{idx + 1}</span>
                          {isDone ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600 dark:text-green-500" />
                          ) : isRunning ? (
                            <Loader2 className="w-3.5 h-3.5 text-[#2D4351] animate-spin" />
                          ) : (
                            <span className="w-2 h-2 rounded-full bg-gray-300" />
                          )}
                        </div>

                        <div>
                          <p className="text-xs font-bold leading-tight line-clamp-2">{step.name}</p>
                          <span className="text-[10px] text-gray-400 block mt-0.5">{step.type}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )))}
      </div>
    </div>
  );
};
