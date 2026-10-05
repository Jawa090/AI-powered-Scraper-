import React from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { useAuth } from '../../context/AuthContext';
import { NotificationsDropdown } from './NotificationsDropdown';
import { SystemHealthBadge } from '../common/SystemHealthBadge';
import { Search, Menu, Building2, LogOut, Shield, User as UserIcon } from 'lucide-react';

interface TopHeaderProps {
  onToggleSidebar: () => void;
  pageTitle: string;
  breadcrumb?: string;
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  onToggleSidebar,
  pageTitle,
  breadcrumb,
}) => {
  const { currentUser, globalSearch, setGlobalSearch } = useDataOps();
  const { role, logout } = useAuth();

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  const displayName = currentUser.name || currentUser.username || 'User';

  return (
    <header className="h-14 bg-white/85 backdrop-blur-md border-b border-[#E5E7EB]/80 px-4 md:px-6 flex items-center justify-between sticky top-0 z-30 shadow-subtle">
      {/* Left: Mobile Menu & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 md:hidden cursor-pointer"
          title="Toggle Navigation"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-semibold text-gray-900 tracking-tight">{pageTitle}</h1>
            {breadcrumb && (
              <span className="text-xs text-[#848485] hidden sm:inline">
                / {breadcrumb}
              </span>
            )}
          </div>
          <p className="text-[11px] text-[#848485] hidden md:block">
            {greeting}, <span className="font-medium text-gray-700">{displayName.split(' ')[0]}</span> •{' '}
            <span className="inline-flex items-center gap-1">
              <Building2 className="w-3 h-3 inline text-gray-400" />
              {currentUser.departmentName || 'Operations'}
            </span>
          </p>
        </div>
      </div>

      {/* Center: Search Bar */}
      <div className="flex-1 max-w-xs md:max-w-md mx-4 hidden sm:block">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={globalSearch}
            onChange={e => setGlobalSearch(e.target.value)}
            placeholder="Search leads, datasets... (Press /)"
            className="w-full bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg pl-9 pr-4 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351] focus:border-[#2D4351] transition-all"
          />
        </div>
      </div>

      {/* Right: Actions, Health Badge, Notifications, Role Badge & Logout */}
      <div className="flex items-center gap-2.5">
        <SystemHealthBadge />
        <NotificationsDropdown />

        {/* User Role Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-[#E5E7EB] bg-gray-50 text-xs">
          {role === 'admin' ? (
            <Shield className="w-3.5 h-3.5 text-amber-600" />
          ) : (
            <UserIcon className="w-3.5 h-3.5 text-indigo-600" />
          )}
          <span className="font-semibold text-gray-800">{displayName}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded uppercase ${
            role === 'admin' ? 'bg-amber-100 text-amber-800' : 'bg-indigo-100 text-indigo-800'
          }`}>
            {role}
          </span>
        </div>

        {/* Logout Button */}
        <button
          onClick={logout}
          title="Sign out of DataOps"
          className="p-1.5 text-gray-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors border border-transparent hover:border-rose-200 cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
