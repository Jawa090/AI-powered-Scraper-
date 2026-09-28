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
  data: {
    name: 'Data Agent',
    title: 'Lead Discovery & Ingestion',
    icon: Database,
    color: 'text-blue-600',
    bg: 'bg-blue-50 border-blue-200',
  },
  research: {
    name: 'Research Agent',
    title: 'Market Intelligence & Sources',
    icon: Search,
    color: 'text-purple-600',
    bg: 'bg-purple-50 border-purple-200',
  },
  sales: {
    name: 'Sales Agent',
    title: 'Lead Prioritization & Scoring',
    icon: Target,
    color: 'text-amber-600',
    bg: 'bg-amber-50 border-amber-200',
  },
  email: {
    name: 'Email Agent',
    title: 'Personalized Outreach Drafting',
    icon: Mail,
    color: 'text-rose-600',
    bg: 'bg-rose-50 border-rose-200',
  },
  growth: {
    name: 'Growth Agent',
    title: 'Expansion Strategy & GTM',
    icon: TrendingUp,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50 border-emerald-200',
  },
  orchestrator: {
    name: 'Orchestrator',
    title: 'Pipeline Coordination',
    icon: Bot,
    color: 'text-indigo-600',
    bg: 'bg-indigo-50 border-indigo-200',
  },
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
          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-100/70 border border-emerald-300 px-2 py-0.5 rounded-full">
            <CheckCircle2 className="w-3 h-3" /> Completed
          </span>
        );
      case 'PARTIAL':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-100/70 border border-amber-300 px-2 py-0.5 rounded-full">
            <Clock className="w-3 h-3" /> Partial Success
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-700 bg-rose-100/70 border border-rose-300 px-2 py-0.5 rounded-full">
            <AlertCircle className="w-3 h-3" /> Pipeline Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-700 bg-indigo-100/70 border border-indigo-300 px-2 py-0.5 rounded-full">
            <Sparkles className="w-3 h-3" /> Multi-Agent Workflow
          </span>
        );
    }
  };

  return (
    <div className="my-3 rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 via-white to-slate-50/50 p-3.5 shadow-sm space-y-3">
      {/* Header Bar */}
      <div className="flex items-center justify-between pb-2 border-b border-indigo-100/60">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-indigo-600 text-white flex items-center justify-center">
            <Sparkles className="w-3.5 h-3.5 text-indigo-200" />
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
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>{agentsInvolved.length || agentSteps.length} Agents Coordinated</span>
        </div>
      </div>

      {/* DAG Step Chain */}
      <div className="space-y-2">
        {agentSteps.map((step, idx) => {
          const cfg = AGENT_CONFIGS[step.agentCode.toLowerCase()] || AGENT_CONFIGS.orchestrator;
          const Icon = cfg.icon;
          const isCompleted = step.status === 'COMPLETED';
          const isFailed = step.status === 'FAILED';
          const isBlocked = step.status === 'BLOCKED';
          const isExpanded = expandedStep === step.taskId;

          return (
            <div
              key={step.taskId || idx}
              className={`rounded-lg border transition-all text-xs ${
                isCompleted
                  ? 'border-gray-200 bg-white hover:border-gray-300'
                  : isFailed
                  ? 'border-rose-200 bg-rose-50/40'
                  : isBlocked
                  ? 'border-amber-200 bg-amber-50/30'
                  : 'border-gray-200 bg-gray-50/50'
              }`}
            >
              <div
                className="p-2.5 flex items-center justify-between cursor-pointer select-none"
                onClick={() => setExpandedStep(isExpanded ? null : step.taskId)}
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
                    <p className="text-[11px] text-gray-600 truncate">{step.purpose}</p>
                  </div>
                </div>

                {/* Status Indicator & Accordion Toggle */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {isCompleted && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Done
                    </span>
                  )}
                  {isFailed && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                      <AlertCircle className="w-3 h-3 text-rose-600" /> Failed
                    </span>
                  )}
                  {isBlocked && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                      <Clock className="w-3 h-3 text-amber-600" /> Blocked
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
                  {step.result?.message && (
                    <div className="p-2 rounded bg-white border border-gray-200 font-mono text-[10px] text-gray-700 whitespace-pre-wrap">
                      {step.result.message}
                    </div>
                  )}
                  {step.error && (
                    <div className="p-2 rounded bg-rose-50 border border-rose-200 text-rose-700 text-[10px]">
                      <strong>Error:</strong> {step.error}
                    </div>
                  )}
                  {step.dependencies && step.dependencies.length > 0 && (
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
