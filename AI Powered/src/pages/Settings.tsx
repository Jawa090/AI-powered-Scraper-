import React, { useState } from 'react';
import { useDataOps } from '../context/DataOpsContext';
import {
  User,
  Shield,
  Bell,
  Sliders,
  Building2,
  Bot,
  Zap,
  CheckCircle2,
  Lock,
} from 'lucide-react';

export const Settings: React.FC = () => {
  const { currentUser, showToast } = useDataOps();
  const isAdmin = currentUser.role === 'admin';

  const [activeTab, setActiveTab] = useState<'profile' | 'notifications' | 'departments' | 'roles' | 'agents'>('profile');

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    showToast('Preferences Saved', 'Your system preferences have been updated.', 'success');
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-gray-900">
          Platform Settings & Configuration
        </h1>
        <p className="text-xs text-[#848485] mt-0.5">
          Manage individual user settings, department allocations, and enterprise permissions
        </p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#E5E7EB] text-xs font-medium text-gray-600 gap-6">
        <button
          onClick={() => setActiveTab('profile')}
          className={`pb-2.5 transition-colors ${
            activeTab === 'profile'
              ? 'border-b-2 border-[#2D4351] text-[#2D4351] font-semibold'
              : 'hover:text-gray-900'
          }`}
        >
          Profile & Security
        </button>
        <button
          onClick={() => setActiveTab('notifications')}
          className={`pb-2.5 transition-colors ${
            activeTab === 'notifications'
              ? 'border-b-2 border-[#2D4351] text-[#2D4351] font-semibold'
              : 'hover:text-gray-900'
          }`}
        >
          Notifications
        </button>

        {isAdmin && (
          <>
            <button
              onClick={() => setActiveTab('departments')}
              className={`pb-2.5 transition-colors ${
                activeTab === 'departments'
                  ? 'border-b-2 border-[#2D4351] text-[#2D4351] font-semibold'
                  : 'hover:text-gray-900'
              }`}
            >
              Departments
            </button>
            <button
              onClick={() => setActiveTab('roles')}
              className={`pb-2.5 transition-colors ${
                activeTab === 'roles'
                  ? 'border-b-2 border-[#2D4351] text-[#2D4351] font-semibold'
                  : 'hover:text-gray-900'
              }`}
            >
              Roles & Permissions
            </button>
            <button
              onClick={() => setActiveTab('agents')}
              className={`pb-2.5 transition-colors ${
                activeTab === 'agents'
                  ? 'border-b-2 border-[#2D4351] text-[#2D4351] font-semibold'
                  : 'hover:text-gray-900'
              }`}
            >
              AI Agents & Models
            </button>
          </>
        )}
      </div>

      {/* Tab Contents */}
      {activeTab === 'profile' && (
        <form onSubmit={handleSave} className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-4">
          <div className="flex items-center gap-4 border-b border-gray-100 pb-4">
            <img src={currentUser.avatar} alt={currentUser.name} className="w-14 h-14 rounded-full object-cover ring-2 ring-gray-100" />
            <div>
              <h3 className="text-sm font-bold text-gray-900">{currentUser.name}</h3>
              <p className="text-xs text-gray-500">{currentUser.roleTitle} • {currentUser.departmentName}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Full Name</label>
              <input
                type="text"
                defaultValue={currentUser.name}
                className="w-full text-xs p-2 bg-white border border-[#E5E7EB] rounded-lg focus:ring-1 focus:ring-[#2D4351]"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">Corporate Email</label>
              <input
                type="email"
                readOnly
                defaultValue={currentUser.email}
                className="w-full text-xs p-2 bg-gray-50 border border-[#E5E7EB] rounded-lg text-gray-600 cursor-not-allowed"
              />
            </div>
          </div>

          <div className="pt-2 flex justify-end">
            <button
              type="submit"
              className="px-4 py-2 text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] rounded-lg shadow-sm"
            >
              Save Profile Changes
            </button>
          </div>
        </form>
      )}

      {activeTab === 'notifications' && (
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-4">
          <h3 className="text-sm font-bold text-gray-900">Alert & Notification Rules</h3>
          <div className="space-y-3 text-xs">
            {[
              { title: 'Dataset Completion Alerts', desc: 'Notify immediately when autonomous agent completes data generation' },
              { title: 'High Intent Lead Replies', desc: 'Real-time alert when prospect replies with demo interest' },
              { title: 'Task & Follow-up Reminders', desc: 'Morning digest of scheduled outbound phone calls' },
              { title: 'Cluster Job Error Telemetry', desc: 'Immediate notification if scraping or MX validation hits throttle' },
            ].map(item => (
              <label key={item.title} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-gray-50 cursor-pointer border border-transparent hover:border-gray-200">
                <input type="checkbox" defaultChecked className="mt-0.5 rounded text-[#2D4351] focus:ring-[#2D4351]" />
                <div>
                  <span className="font-semibold text-gray-900 block">{item.title}</span>
                  <span className="text-gray-500">{item.desc}</span>
                </div>
              </label>
            ))}
          </div>
        </div>
      )}

      {isAdmin && activeTab === 'departments' && (
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-4">
          <h3 className="text-sm font-bold text-gray-900">Enterprise Department Quotas</h3>
          <p className="text-xs text-gray-500">Allocated monthly lead generation and scraping credit budgets.</p>
          <div className="divide-y divide-gray-100 text-xs">
            {['Sales 1', 'Sales 2', 'Email Marketing', 'Business Development', 'Research'].map(dept => (
              <div key={dept} className="py-2.5 flex items-center justify-between">
                <span className="font-semibold text-gray-900">{dept}</span>
                <span className="text-gray-500 font-mono">15,000 Verified Leads / Month</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {isAdmin && activeTab === 'roles' && (
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-4">
          <h3 className="text-sm font-bold text-gray-900">Roles & Permission Matrix</h3>
          <div className="p-3 bg-white text-blue-900 border border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 rounded-lg text-xs leading-relaxed">
            Admin has global permission. Sales & Email Marketing representatives have scoped workspace access limited to direct calling and email campaigns.
          </div>
        </div>
      )}

      {isAdmin && activeTab === 'agents' && (
        <div className="bg-white border border-[#E5E7EB] rounded-xl p-6 shadow-card space-y-4">
          <h3 className="text-sm font-bold text-gray-900">AI Intelligence Core Config</h3>
          <div className="space-y-3 text-xs">
            <div className="flex justify-between items-center py-2 border-b border-gray-100">
              <div>
                <span className="font-semibold text-gray-900 block">Default Reasoning Engine</span>
                <span className="text-gray-500">DataOps Neural v4.2 Cross-Questioning Model</span>
              </div>
              <span className="font-mono text-green-600 dark:text-green-500 font-semibold bg-white border-green-200 dark:bg-black dark:border-green-800 px-2 py-0.5 rounded border">
                Active
              </span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-100">
              <div>
                <span className="font-semibold text-gray-900 block">Deduplication Matching Engine</span>
                <span className="text-gray-500">Strict corporate entity & root domain matching</span>
              </div>
              <span className="font-mono text-green-600 dark:text-green-500 font-semibold bg-white border-green-200 dark:bg-black dark:border-green-800 px-2 py-0.5 rounded border">
                Enabled
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
