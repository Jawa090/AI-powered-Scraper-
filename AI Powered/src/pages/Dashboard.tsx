import React from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { MetricCard } from '../components/common/MetricCard';
import { DepartmentPerformanceTable } from '../components/dashboard/DepartmentPerformanceTable';
import { ActivityOverviewChart } from '../components/dashboard/ActivityOverviewChart';
import { RecentActivityList } from '../components/dashboard/RecentActivityList';
import {
  Users2,
  Sparkles,
  PhoneCall,
  Mail,
  ThumbsUp,
  ClockAlert,
  ArrowUpRight,
  TrendingUp,
} from 'lucide-react';

interface DashboardProps {
  onNavigate: (path: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const { kpis, departments, activities } = useDataOps();

  return (
    <div className="space-y-6">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            Operations Overview
          </h1>
          <p className="text-xs text-[#848485] mt-0.5">
            Monitor data generation, outreach activity and department performance.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('/agent')}
            className="px-3.5 py-2 rounded-lg bg-[#2D4351] text-white hover:bg-[#20313C] text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-green-400" />
            <span>Launch AI Data Request</span>
          </button>
        </div>
      </div>

      {/* 6 Top KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <MetricCard
          title="Total Leads"
          value={kpis.totalLeads}
          change="+14.2%"
          changeType="positive"
          subtext="Across all datasets"
          icon={Users2}
          onClick={() => onNavigate('/leads')}
        />
        <MetricCard
          title="Generated Today"
          value={kpis.generatedToday}
          change="+8.4%"
          changeType="positive"
          subtext="Active pipelines"
          icon={Sparkles}
          onClick={() => onNavigate('/datasets')}
        />
        <MetricCard
          title="Calls Completed"
          value={kpis.callsCompleted}
          change="+12.0%"
          changeType="positive"
          subtext="Direct dial reps"
          icon={PhoneCall}
          onClick={() => onNavigate('/leads')}
        />
        <MetricCard
          title="Emails Sent"
          value={kpis.emailsSent}
          change="+24.5%"
          changeType="positive"
          subtext="MX verified inboxes"
          icon={Mail}
          onClick={() => onNavigate('/leads')}
        />
        <MetricCard
          title="Interested Leads"
          value={kpis.interestedLeads}
          change="+18.3%"
          changeType="positive"
          subtext="High pipeline intent"
          icon={ThumbsUp}
          onClick={() => onNavigate('/leads')}
        />
        <MetricCard
          title="Pending Actions"
          value={kpis.pendingActions}
          change="-5.2%"
          changeType="neutral"
          subtext="Queued rep tasks"
          icon={ClockAlert}
          onClick={() => onNavigate('/gantt')}
        />
      </div>

      {/* Department Performance Matrix */}
      <div>
        <DepartmentPerformanceTable
          departments={departments}
          onSelectDepartment={() => onNavigate('/departments')}
        />
      </div>

      {/* Bottom Grid: Activity Overview Chart & Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <ActivityOverviewChart />
        </div>
        <div className="lg:col-span-1">
          <RecentActivityList
            activities={activities}
            onSelectActivity={act => {
              if (act.leadId) onNavigate('/leads');
              else if (act.datasetId) onNavigate('/datasets');
            }}
          />
        </div>
      </div>
    </div>
  );
};
