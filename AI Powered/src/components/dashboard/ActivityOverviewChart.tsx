import React, { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

export const ActivityOverviewChart: React.FC = () => {
  const [range, setRange] = useState<'7d' | '30d' | '90d'>('7d');
  const data: any[] = [];

  return (
    <div className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card">
      {/* Chart Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Activity Overview</h3>
          <p className="text-xs text-[#848485]">Multi-channel calls, emails dispatched, and leads generated</p>
        </div>

        {/* Range Selector */}
        <div className="flex items-center bg-[#F8F9FA] p-0.5 rounded-lg border border-[#E5E7EB] text-xs">
          {(['7d', '30d', '90d'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setRange(tab)}
              className={`px-3 py-1 rounded-md font-medium transition-all ${
                range === tab
                  ? 'bg-[#2D4351] text-white shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {tab === '7d' ? '7 Days' : tab === '30d' ? '30 Days' : '90 Days'}
            </button>
          ))}
        </div>
      </div>

      {/* Recharts Area Container */}
      <div className="h-64 w-full">
        {!data || data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-gray-400">
            No activity data recorded yet.
          </div>
        ) : (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#2D4351" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#2D4351" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorEmails" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorLeads" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10B981" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F3F5" />
            <XAxis
              dataKey="name"
              stroke="#848485"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <YAxis
              stroke="#848485"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={value => (value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#FFFFFF',
                borderRadius: '8px',
                border: '1px solid #E5E7EB',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.05)',
                fontSize: '12px',
              }}
            />
            <Legend
              verticalAlign="top"
              align="right"
              iconType="circle"
              wrapperStyle={{ fontSize: '11px', paddingBottom: '10px' }}
            />
            <Area
              type="monotone"
              dataKey="calls"
              name="Calls Completed"
              stroke="#2D4351"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorCalls)"
            />
            <Area
              type="monotone"
              dataKey="emails"
              name="Emails Sent"
              stroke="#8B5CF6"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorEmails)"
            />
            <Area
              type="monotone"
              dataKey="leads"
              name="Leads Generated"
              stroke="#10B981"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#colorLeads)"
            />
          </AreaChart>
        </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};
