import React from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { useAuth } from '../../context/AuthContext';
import { NotificationsDropdown } from './NotificationsDropdown';
import { SystemHealthBadge } from '../common/SystemHealthBadge';
import { Search, Menu, Building2, LogOut, Shield, User as UserIcon, Moon, Sun } from 'lucide-react';
import { useDarkMode } from '../../hooks/useDarkMode';

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
  const { isDark, toggle } = useDarkMode();

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  const displayName = currentUser.name || currentUser.username || 'User';

  return (
    <header className="h-14 bg-white/85 dark:bg-black/85 backdrop-blur-md border-b border-[#E5E7EB]/80 dark:border-gray-800 px-4 md:px-6 flex items-center justify-between sticky top-0 z-30 shadow-subtle transition-colors">
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
            <h1 className="text-sm font-semibold text-gray-900 dark:text-golden-500 tracking-tight">{pageTitle}</h1>
            {breadcrumb && (
              <span className="text-xs text-[#848485] hidden sm:inline">
                / {breadcrumb}
              </span>
            )}
          </div>
          <p className="text-[11px] text-[#848485] hidden md:block">
            {greeting}, <span className="font-medium text-gray-700 dark:text-golden-400">{displayName.split(' ')[0]}</span> •{' '}
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
            className="w-full bg-[#F8F9FA] dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 rounded-lg pl-9 pr-4 py-1.5 text-xs text-gray-900 dark:text-golden-100 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500 focus:border-[#2D4351] dark:focus:border-golden-500 transition-all"
          />
        </div>
      </div>

      {/* Right: Actions, Health Badge, Notifications, Role Badge & Logout */}
      <div className="flex items-center gap-2.5">
        <SystemHealthBadge />
        <NotificationsDropdown />

        {/* Dark Mode Toggle */}
        <button
          onClick={toggle}
          title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
          className="p-1.5 text-gray-500 hover:text-golden-500 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors border border-transparent cursor-pointer"
        >
          {isDark ? <Sun className="w-4 h-4 text-golden-500" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* User Role Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-[#E5E7EB] dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-xs">
          {role === 'admin' ? (
            <Shield className="w-3.5 h-3.5 text-blue-600" />
          ) : (
            <UserIcon className="w-3.5 h-3.5 text-blue-600" />
          )}
          <span className="font-semibold text-gray-800 dark:text-gray-200">{displayName}</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded uppercase border ${
            role === 'admin' ? 'bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800' : 'bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800'
          }`}>
            {role}
          </span>
        </div>

        {/* Logout Button */}
        <button
          onClick={logout}
          title="Sign out of DataOps"
          className="p-1.5 text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-500 dark:hover:bg-red-900/30 rounded-lg transition-colors border border-transparent hover:border-red-200 dark:hover:border-red-800 cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
