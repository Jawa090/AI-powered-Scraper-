import React from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { useAuth } from '../../context/AuthContext';
import {
  Bot,
  Database,
  Users2,
  ActivitySquare,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  UserCheck,
} from 'lucide-react';

interface SidebarProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentPath,
  onNavigate,
  isCollapsed,
  onToggleCollapse,
  isOpenMobile,
  onCloseMobile,
}) => {
  const { leads } = useDataOps();
  const { role } = useAuth();
  const isAdmin = role === 'admin';

  interface NavItem {
    label: string;
    path: string;
    icon: React.ComponentType<{ className?: string }>;
    badge?: string | number;
    badgeColor?: string;
    adminOnly?: boolean;
  }

  // P13.6: Keep Agent, Leads, Datasets, Jobs, Settings, and Admin pages
  const primaryNav: NavItem[] = [
    { label: 'AI Agent', path: '/agent', icon: Bot, badge: 'Active', badgeColor: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    { label: 'Leads', path: '/leads', icon: Users2, badge: leads.length },
    { label: 'Datasets', path: '/datasets', icon: Database },
    { label: 'Jobs', path: '/jobs', icon: ActivitySquare, badge: 'Live', badgeColor: 'bg-sky-50 text-sky-700 border-sky-200' },
  ];

  const adminNav: NavItem[] = [
    { label: 'Users', path: '/admin/users', icon: UserCheck, adminOnly: true },
    { label: 'Activity Logs', path: '/admin/activity', icon: ActivitySquare, adminOnly: true },
    { label: 'Knowledge Base', path: '/admin/kb', icon: Database, adminOnly: true },
  ];

  const handleItemClick = (path: string) => {
    onNavigate(path);
    onCloseMobile();
  };

  const renderNavList = (items: NavItem[], sectionTitle?: string) => {
    const visibleItems = items.filter(item => {
      if (item.adminOnly && !isAdmin) return false;
      return true;
    });

    if (visibleItems.length === 0) return null;

    return (
      <div className="mb-4">
        {sectionTitle && !isCollapsed && (
          <p className="px-3 mb-1.5 text-[10px] font-semibold tracking-wider text-[#848485] uppercase">
            {sectionTitle}
          </p>
        )}
        <div className="space-y-0.5">
          {visibleItems.map(item => {
            const isActive = currentPath === item.path || (item.path !== '/agent' && currentPath.startsWith(item.path));
            const Icon = item.icon;

            return (
              <button
                key={item.path}
                onClick={() => handleItemClick(item.path)}
                title={isCollapsed ? item.label : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all group cursor-pointer ${
                  isActive
                    ? 'bg-[#2D4351] text-white shadow-sm'
                    : 'text-gray-700 hover:bg-gray-100/80 hover:text-gray-900'
                }`}
              >
                <Icon
                  className={`w-4 h-4 flex-shrink-0 transition-colors ${
                    isActive ? 'text-white' : 'text-gray-500 group-hover:text-gray-800'
                  }`}
                />
                {!isCollapsed && (
                  <span className="flex-1 text-left truncate">{item.label}</span>
                )}
                {!isCollapsed && item.badge !== undefined && (
                  <span
                    className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ml-auto ${
                      isActive
                        ? 'bg-white/20 text-white border-transparent'
                        : item.badgeColor || 'bg-gray-100 text-gray-600 border-gray-200'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpenMobile && (
        <div
          className="fixed inset-0 bg-black/40 z-40 md:hidden backdrop-blur-[2px]"
          onClick={onCloseMobile}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-40 bg-white/90 backdrop-blur-md border-r border-[#E5E7EB]/80 flex flex-col transition-all duration-200 ${
          isCollapsed ? 'w-16' : 'w-60'
        } ${isOpenMobile ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
      >
        {/* Brand Header */}
        <div className="h-14 flex items-center justify-between px-4 border-b border-[#E5E7EB]">
          <div
            onClick={() => handleItemClick('/agent')}
            className="flex items-center gap-2.5 cursor-pointer select-none"
          >
            <div className="w-8 h-8 rounded-lg bg-[#2D4351] flex items-center justify-center text-white shadow-sm flex-shrink-0">
              <Sparkles className="w-4 h-4 text-emerald-400" />
            </div>
            {!isCollapsed && (
              <div className="min-w-0">
                <span className="text-sm font-bold tracking-tight text-[#111827] block leading-tight">
                  DataOps AI
                </span>
                <span className="text-[10px] text-[#848485] tracking-wider uppercase block">
                  Enterprise Ops
                </span>
              </div>
            )}
          </div>

          <button
            onClick={onToggleCollapse}
            className="hidden md:flex p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors cursor-pointer"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Scrollable Navigation List */}
        <div className="flex-1 overflow-y-auto px-3 py-4">
          {renderNavList(primaryNav, 'Operations')}
          {isAdmin && renderNavList(adminNav, 'Admin Center')}
        </div>

        {/* Bottom Navigation / Settings */}
        <div className="p-3 border-t border-[#E5E7EB] space-y-1">
          <button
            onClick={() => handleItemClick('/settings')}
            title={isCollapsed ? 'Settings' : undefined}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer ${
              currentPath === '/settings'
                ? 'bg-[#2D4351] text-white'
                : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'
            }`}
          >
            <Settings className="w-4 h-4 flex-shrink-0 text-gray-500" />
            {!isCollapsed && <span>Settings</span>}
          </button>
        </div>
      </aside>
    </>
  );
};
