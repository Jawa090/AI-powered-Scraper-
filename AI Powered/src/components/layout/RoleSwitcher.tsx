import React, { useState, useRef, useEffect } from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { UserRole } from '../../types';
import { Shield, ChevronDown, Check, UserCheck } from 'lucide-react';

export const RoleSwitcher: React.FC = () => {
  const { currentUser, switchRole, allUsers, switchUser } = useDataOps();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const roles: { role: UserRole; label: string; user: string; dept: string }[] = [
    { role: 'sales', label: 'Sales Employee', user: 'Ahmed Khan', dept: 'Sales 1' },
    { role: 'email', label: 'Email Mktg Employee', user: 'Sara Jenkins', dept: 'Email Marketing' },
    { role: 'manager', label: 'Department Manager', user: 'Marcus Vance', dept: 'Sales 1 & Revenue' },
    { role: 'admin', label: 'Admin (Full Access)', user: 'Elena Rostova', dept: 'Enterprise Admin' },
  ];

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-[#E5E7EB] bg-white hover:bg-gray-50 text-xs text-gray-700 transition-colors shadow-sm"
        title="Switch simulated user role"
      >
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="font-medium text-gray-900">{currentUser.name}</span>
        <span className="text-[11px] text-[#848485] px-1.5 py-0.5 bg-gray-100 rounded">
          {currentUser.role.toUpperCase()}
        </span>
        <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-white rounded-xl shadow-dropdown border border-[#E5E7EB] py-2 z-50 animate-in fade-in zoom-in-95">
          <div className="px-3.5 py-2 border-b border-gray-100">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[#848485]">
              Simulate Persona / Role
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              Switch roles to verify permissions & custom workflows
            </p>
          </div>

          <div className="py-1">
            {roles.map(r => {
              const isCurrent = currentUser.role === r.role;
              return (
                <button
                  key={r.role}
                  onClick={() => {
                    switchRole(r.role);
                    setIsOpen(false);
                  }}
                  className={`w-full text-left px-3.5 py-2 flex items-center justify-between hover:bg-gray-50 transition-colors ${
                    isCurrent ? 'bg-[#EAEFF2]/50' : ''
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-gray-900">{r.label}</span>
                      {r.role === 'admin' && (
                        <Shield className="w-3 h-3 text-amber-500 inline" />
                      )}
                    </div>
                    <p className="text-[11px] text-gray-500">
                      {r.user} • <span className="text-gray-400">{r.dept}</span>
                    </p>
                  </div>
                  {isCurrent && <Check className="w-4 h-4 text-[#2D4351] ml-2 flex-shrink-0" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
