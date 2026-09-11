import React from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { NotificationsDropdown } from './NotificationsDropdown';
import { RoleSwitcher } from './RoleSwitcher';
import { Search, Menu, Sparkles, Building2 } from 'lucide-react';

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

  // Dynamic time greeting
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  return (
    <header className="h-14 bg-white border-b border-[#E5E7EB] px-4 md:px-6 flex items-center justify-between sticky top-0 z-30">
      {/* Left: Mobile Menu & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 md:hidden"
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
            {greeting}, <span className="font-medium text-gray-700">{currentUser.name.split(' ')[0]}</span> •{' '}
            <span className="inline-flex items-center gap-1">
              <Building2 className="w-3 h-3 inline text-gray-400" />
              {currentUser.departmentName}
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
            placeholder="Search leads, datasets, campaigns... (Press /)"
            className="w-full bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg pl-9 pr-4 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-[#2D4351] focus:border-[#2D4351] transition-all"
          />
        </div>
      </div>

      {/* Right: Actions, Notifications, Role Switcher */}
      <div className="flex items-center gap-2.5">
        <NotificationsDropdown />
        <RoleSwitcher />

        {/* User Profile Pill */}
        <div className="flex items-center gap-2 pl-2 border-l border-gray-200">
          <img
            src={currentUser.avatar}
            alt={currentUser.name}
            className="w-7 h-7 rounded-full object-cover ring-1 ring-gray-200"
          />
        </div>
      </div>
    </header>
  );
};
