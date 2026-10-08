import React, { useState } from 'react';
import { AgentTaskStep } from '../../types';
import {
  Database,
  Search,
  Target,
  Mail,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Bot,
  Sparkles,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';

interface MultiAgentWorkflowVisualizerProps {
  collaborationId?: string | null;
  collaborationStatus?: string | null;
  agentsInvolved?: string[];
  agentSteps?: AgentTaskStep[];
}

const AGENT_CONFIGS: Record<
  string,
  { name: string; title: string; icon: React.ComponentType<{ className?: string }>; color: string; bg: string }
> = {
  data: { name: 'Data Agent', title: 'Lead Discovery & Ingestion', icon: Database, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  database: { name: 'Database Agent', title: 'Local Repository & Index Query', icon: Database, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  research: { name: 'Research Agent', title: 'Market Intelligence & Sources', icon: Search, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  sales: { name: 'Sales Agent', title: 'Lead Prioritization & Scoring', icon: Target, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  email: { name: 'Email Agent', title: 'Personalized Outreach Drafting', icon: Mail, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  growth: { name: 'Growth Agent', title: 'Expansion Strategy & GTM', icon: TrendingUp, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  scraper: { name: 'Scraper Engine', title: 'Autonomous Web Extraction', icon: Bot, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  bonfire: { name: 'Bonfire Agent', title: 'Dallas City Hall Portal', icon: Bot, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  dasny: { name: 'DASNY Agent', title: 'NY Construction Portal', icon: Bot, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  jwiz: { name: 'JWiz Agent', title: 'Jewish Business Directory', icon: Bot, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  nyscr: { name: 'NYSCR Agent', title: 'NY State Contract Reporter', icon: Bot, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
  orchestrator: { name: 'Orchestrator', title: 'Pipeline Coordination', icon: Bot, color: 'text-blue-600 dark:text-blue-500', bg: 'bg-white border-blue-200 dark:bg-black dark:border-blue-800' },
};

export const MultiAgentWorkflowVisualizer: React.FC<MultiAgentWorkflowVisualizerProps> = ({
  collaborationId,
  collaborationStatus,
  agentsInvolved = [],
  agentSteps = [],
}) => {
  const [expandedStep, setExpandedStep] = useState<string | null>(null);

  if (!collaborationId && (!agentSteps || agentSteps.length <= 1)) {
    return null;
  }

  const statusBadge = () => {
    switch (collaborationStatus?.toUpperCase()) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 border px-2 py-0.5 rounded-full">
            <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-500" /> Completed
          </span>
        );
      case 'PARTIAL':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 border px-2 py-0.5 rounded-full">
            <Clock className="w-3 h-3 text-blue-600 dark:text-blue-500" /> Partial Success
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-red-600 border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 border px-2 py-0.5 rounded-full">
            <AlertCircle className="w-3 h-3 text-red-600 dark:text-red-500" /> Pipeline Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 border px-2 py-0.5 rounded-full">
            <Sparkles className="w-3 h-3 text-blue-600 dark:text-blue-500" /> Multi-Agent Workflow
          </span>
        );
    }
  };

  return (
    <div className="my-3 rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50/40 via-white to-slate-50/50 p-3.5 shadow-sm space-y-3">
      {/* Header Bar */}
      <div className="flex items-center justify-between pb-2 border-b border-blue-100/60">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-blue-600 text-white flex items-center justify-center">
            <Sparkles className="w-3.5 h-3.5 text-blue-200" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-gray-900">Multi-Agent Collaboration Pipeline</span>
              {statusBadge()}
            </div>
            {collaborationId && (
              <span className="text-[10px] font-mono text-gray-400 block">{collaborationId}</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 text-[11px] text-gray-500 font-medium">
          <ShieldCheck className="w-3.5 h-3.5 text-green-600" />
          <span>{agentsInvolved.length || agentSteps.length} Agents Coordinated</span>
        </div>
      </div>

      {/* DAG Step Chain */}
      <div className="space-y-2">
        {agentSteps.map((step, idx) => {
          if (!step) return null;

          const rawCode =
            step.agentCode ||
            (step as any).agent_code ||
            (step as any).agent ||
            (step as any).agentName ||
            'orchestrator';
          const agentKey = String(rawCode).toLowerCase().trim();
          const cfg = AGENT_CONFIGS[agentKey] || AGENT_CONFIGS.orchestrator;
          const Icon = cfg.icon;

          const stepId =
            step.taskId ||
            (step as any).task_id ||
            (step as any).step_id ||
            (step as any).id ||
            `step-${idx}`;

          const purpose =
            step.purpose ||
            (step as any).action ||
            (step as any).title ||
            (step as any).description ||
            'Automated Pipeline Step';

          const rawStatus = (step.status || (step as any).status || 'PENDING').toString().toUpperCase();
          const isCompleted = rawStatus === 'COMPLETED' || rawStatus === 'SUCCESS';
          const isFailed = rawStatus === 'FAILED' || rawStatus === 'ERROR';
          const isBlocked = rawStatus === 'BLOCKED';
          const isExpanded = expandedStep === stepId;

          return (
            <div
              key={stepId}
              className={`rounded-lg border transition-all text-xs ${
                isCompleted
                  ? 'border-gray-200 bg-white hover:border-gray-300 dark:bg-gray-900 dark:border-gray-800'
                  : isFailed
                  ? 'bg-red-50/40 border-red-200 dark:bg-red-900/10 dark:border-red-800'
                  : isBlocked
                  ? 'bg-blue-50/30 border-blue-200 dark:bg-blue-900/10 dark:border-blue-800'
                  : 'border-gray-200 bg-gray-50/50 dark:bg-gray-800/50 dark:border-gray-700'
              }`}
            >
              <div
                className="p-2.5 flex items-center justify-between cursor-pointer select-none"
                onClick={() => setExpandedStep(isExpanded ? null : stepId)}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  {/* Step Order Circle */}
                  <span className="w-5 h-5 rounded-full bg-gray-100 text-gray-700 font-bold text-[10px] flex items-center justify-center flex-shrink-0">
                    {idx + 1}
                  </span>

                  {/* Agent Icon Badge */}
                  <div
                    className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 border ${cfg.bg}`}
                  >
                    <Icon className={`w-3.5 h-3.5 ${cfg.color}`} />
                  </div>

                  {/* Agent Title & Purpose */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-gray-900">{cfg.name}</span>
                      <span className="text-[10px] text-gray-400">({cfg.title})</span>
                    </div>
                    <p className="text-[11px] text-gray-600 truncate">{purpose}</p>
                  </div>
                </div>

                {/* Status Indicator & Accordion Toggle */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {isCompleted && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800 border px-2 py-0.5 rounded">
                      <CheckCircle2 className="w-3 h-3 text-green-600 dark:text-green-500" /> Done
                    </span>
                  )}
                  {isFailed && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-red-600 border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 border px-2 py-0.5 rounded">
                      <AlertCircle className="w-3 h-3 text-red-600 dark:text-red-500" /> Failed
                    </span>
                  )}
                  {isBlocked && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 border px-2 py-0.5 rounded">
                      <Clock className="w-3 h-3 text-blue-600 dark:text-blue-500" /> Blocked
                    </span>
                  )}

                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  )}
                </div>
              </div>

              {/* Accordion Detail View */}
              {isExpanded && (
                <div className="px-3 pb-3 pt-1 border-t border-gray-100 text-[11px] space-y-1.5 bg-gray-50/50 rounded-b-lg">
                  {step.result && (
                    <div className="p-2 rounded bg-white border border-gray-200 font-mono text-[10px] text-gray-700 whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {typeof step.result === 'string'
                        ? step.result
                        : step.result.message || JSON.stringify(step.result, null, 2)}
                    </div>
                  )}
                  {step.error && (
                    <div className="p-2 rounded bg-white text-red-600 border border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 text-[10px]">
                      <strong>Error:</strong> {typeof step.error === 'string' ? step.error : JSON.stringify(step.error)}
                    </div>
                  )}
                  {Array.isArray(step.dependencies) && step.dependencies.length > 0 && (
                    <p className="text-gray-400 text-[10px]">
                      <strong>Prerequisites:</strong> {step.dependencies.join(', ')}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
