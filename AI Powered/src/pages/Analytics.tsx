import React from 'react';
import { ConversionFunnel } from '../components/analytics/ConversionFunnel';
import { ActivityOverviewChart } from '../components/dashboard/ActivityOverviewChart';
import { MetricCard } from '../components/common/MetricCard';
import { useDataOps } from '../context/DataOpsContext';
import {
  BarChart3,
  TrendingUp,
  Award,
  ShieldCheck,
  CheckCircle2,
  Users2,
  PhoneCall,
  Mail,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export const Analytics: React.FC = () => {
  const { departments } = useDataOps();

  const deptComparisonData = departments.map(d => ({
    name: d.name,
    called: d.calledCount,
    emailed: d.emailedCount,
    interested: d.interestedCount,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-gray-900">
          Executive Intelligence Analytics
        </h1>
        <p className="text-xs text-[#848485] mt-0.5">
          End-to-end pipeline metrics, conversion velocity, and departmental productivity
        </p>
      </div>

      {/* Top Conversion Funnel & Outreach Trends */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ConversionFunnel />
        <ActivityOverviewChart />
      </div>

      {/* Department Channel Distribution Chart */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-card">
        <div className="flex items-center justify-between mb-4 border-b border-[#E5E7EB] pb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Department Channel Comparison</h3>
            <p className="text-xs text-[#848485]">Calls logged vs. Emails delivered per business unit</p>
          </div>
          <span className="text-xs font-semibold text-[#2D4351] bg-[#EAEFF2] px-2 py-0.5 rounded">
            Channel Volume
          </span>
        </div>

        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={deptComparisonData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F3F5" />
              <XAxis dataKey="name" stroke="#848485" fontSize={11} tickLine={false} />
              <YAxis stroke="#848485" fontSize={11} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '8px',
                  border: '1px solid #E5E7EB',
                  fontSize: '12px',
                }}
              />
              <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: '11px', paddingBottom: '10px' }} />
              <Bar dataKey="called" name="Calls Completed" fill="#2D4351" radius={[4, 4, 0, 0]} />
              <Bar dataKey="emailed" name="Emails Sent" fill="#8B5CF6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="interested" name="Interested" fill="#10B981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Data Quality & Deliverability Telemetry */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-700 mb-1">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Email Deliverability Score</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 font-mono">99.2%</p>
          <p className="text-xs text-emerald-700 mt-1">Live SMTP MX handshakes active</p>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-700 mb-1">
            <PhoneCall className="w-4 h-4 text-blue-600" />
            <span>Direct Dial Connect Rate</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 font-mono">34.8%</p>
          <p className="text-xs text-blue-700 mt-1">Validated HQ and mobile switches</p>
        </div>

        <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-700 mb-1">
            <CheckCircle2 className="w-4 h-4 text-[#2D4351]" />
            <span>Deduplication Accuracy</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 font-mono">100%</p>
          <p className="text-xs text-gray-500 mt-1">Zero cross-department rep collision</p>
        </div>
      </div>
    </div>
  );
};
