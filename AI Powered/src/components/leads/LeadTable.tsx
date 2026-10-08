import React, { useState, useMemo } from 'react';
import { Lead, LeadStatus } from '../../types';
import { StatusBadge } from '../common/StatusBadge';
import {
  Search,
  Filter,
  Phone,
  Mail,
  MoreHorizontal,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  CheckSquare,
  Square,
  Building2,
} from 'lucide-react';

interface LeadTableProps {
  leads: Lead[];
  onSelectLead?: (lead: Lead) => void;
  onCallLead?: (lead: Lead) => void;
  onEmailLead?: (lead: Lead) => void;
  onOpenBulkEmail?: (selectedLeads: Lead[]) => void;
  compact?: boolean;
}

export const LeadTable: React.FC<LeadTableProps> = ({
  leads,
  onSelectLead,
  onCallLead,
  onEmailLead,
  onOpenBulkEmail,
  compact = false,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Filtered leads
  const filteredLeads = useMemo(() => {
    return leads.filter(l => {
      if (departmentFilter !== 'all' && l.departmentId !== departmentFilter) return false;
      if (statusFilter !== 'all' && l.status !== statusFilter) return false;
      if (searchTerm) {
        const q = searchTerm.toLowerCase();
        return (
          Boolean(l.name?.toLowerCase().includes(q)) ||
          Boolean(l.company?.toLowerCase().includes(q)) ||
          Boolean(l.title?.toLowerCase().includes(q)) ||
          Boolean(l.email?.toLowerCase().includes(q)) ||
          Boolean(l.location?.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [leads, departmentFilter, statusFilter, searchTerm]);

  // Paginated leads
  const totalPages = Math.ceil(filteredLeads.length / pageSize) || 1;
  const paginatedLeads = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredLeads.slice(start, start + pageSize);
  }, [filteredLeads, currentPage]);

  const toggleSelectAll = () => {
    if (selectedIds.length === paginatedLeads.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(paginatedLeads.map(l => l.id));
    }
  };

  const toggleSelectOne = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
    );
  };

  const selectedLeadObjects = useMemo(() => {
    return leads.filter(l => selectedIds.includes(l.id));
  }, [leads, selectedIds]);

  return (
    <div className="bg-white dark:bg-black border border-[#E5E7EB] dark:border-gray-800 rounded-xl shadow-card overflow-hidden transition-colors">
      {/* Top Filter Bar */}
      <div className="p-4 border-b border-[#E5E7EB] dark:border-gray-800 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between bg-white dark:bg-black">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={e => {
              setSearchTerm(e.target.value);
              setCurrentPage(1);
            }}
            placeholder="Search leads, companies, locations..."
            className="w-full bg-[#F8F9FA] dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-gray-900 dark:text-golden-100 placeholder:text-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Department filter */}
          <select
            value={departmentFilter}
            onChange={e => {
              setDepartmentFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="text-xs bg-[#F8F9FA] dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 rounded-lg px-2.5 py-1.5 text-gray-700 dark:text-golden-300 focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
          >
            <option value="all">All Departments</option>
            <option value="dept-sales-1">Sales 1</option>
            <option value="dept-sales-2">Sales 2</option>
            <option value="dept-email-mktg">Email Marketing</option>
            <option value="dept-biz-dev">Business Development</option>
            <option value="dept-research">Research</option>
          </select>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={e => {
              setStatusFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="text-xs bg-[#F8F9FA] dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 rounded-lg px-2.5 py-1.5 text-gray-700 dark:text-golden-300 focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
          >
            <option value="all">All Statuses</option>
            <option value="New">New</option>
            <option value="Called">Called</option>
            <option value="Emailed">Emailed</option>
            <option value="Interested">Interested</option>
            <option value="Follow Up">Follow Up</option>
            <option value="Qualified">Qualified</option>
          </select>
        </div>
      </div>

      {/* Bulk Action Bar (Visible when rows are selected) */}
      {selectedIds.length > 0 && (
        <div className="bg-[#EAEFF2] border-b border-[#2D4351]/20 px-4 py-2 flex items-center justify-between animate-in fade-in">
          <span className="text-xs font-semibold text-[#2D4351]">
            {selectedIds.length} lead{selectedIds.length > 1 ? 's' : ''} selected
          </span>
          <div className="flex items-center gap-2">
            {onOpenBulkEmail && (
              <button
                onClick={() => onOpenBulkEmail(selectedLeadObjects)}
                className="px-3 py-1 rounded-md text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] transition-colors flex items-center gap-1.5 shadow-sm"
              >
                <Mail className="w-3.5 h-3.5 text-blue-300" />
                <span>Email Selected ({selectedIds.length})</span>
              </button>
            )}
            <button
              onClick={() => setSelectedIds([])}
              className="px-2.5 py-1 text-xs text-gray-600 hover:text-gray-900"
            >
              Deselect All
            </button>
          </div>
        </div>
      )}

      {/* High-density Enterprise Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#E5E7EB] dark:border-gray-800 bg-[#F8F9FA] dark:bg-gray-900 text-[#848485] dark:text-golden-600 font-semibold">
              <th className="py-2.5 px-3 w-8 text-center">
                <input
                  type="checkbox"
                  checked={
                    paginatedLeads.length > 0 &&
                    selectedIds.length === paginatedLeads.length
                  }
                  onChange={toggleSelectAll}
                  className="rounded border-gray-300 text-[#2D4351] focus:ring-[#2D4351]"
                />
              </th>
              <th className="py-2.5 px-3">Contact Name</th>
              <th className="py-2.5 px-3">Company</th>
              <th className="py-2.5 px-3">Title</th>
              <th className="py-2.5 px-3">Email</th>
              <th className="py-2.5 px-3">Phone</th>
              <th className="py-2.5 px-3">Location</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Assigned Rep</th>
              <th className="py-2.5 px-3">Last Activity</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {paginatedLeads.length === 0 ? (
              <tr>
                <td colSpan={11} className="py-8 text-center text-gray-400">
                  No leads found matching criteria.
                </td>
              </tr>
            ) : (
              paginatedLeads.map(lead => {
                const isSelected = selectedIds.includes(lead.id);
                return (
                  <tr
                    key={lead.id}
                    onClick={() => onSelectLead?.(lead)}
                    className={`hover:bg-[#F8F9FA]/80 dark:hover:bg-gray-800/50 transition-colors cursor-pointer ${
                      isSelected ? 'bg-[#EAEFF2]/40 dark:bg-golden-900/20' : ''
                    }`}
                  >
                    <td
                      className="py-2 px-3 text-center"
                      onClick={e => toggleSelectOne(lead.id, e)}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => {}}
                        className="rounded border-gray-300 text-[#2D4351] focus:ring-[#2D4351]"
                      />
                    </td>
                    <td className="py-2 px-3 font-semibold text-gray-900 dark:text-golden-100 whitespace-nowrap">
                      {lead.name || lead.company || '—'}
                    </td>
                    <td className="py-2 px-3 text-gray-700 dark:text-golden-300 whitespace-nowrap">
                      {lead.company || '—'}
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-golden-400 truncate max-w-[150px]">
                      {lead.title || '—'}
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-golden-400 truncate max-w-[160px]">
                      <span className="font-mono text-[11px]">{lead.email || '—'}</span>
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-golden-400 font-mono text-[11px] whitespace-nowrap">
                      {lead.phone || '—'}
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-golden-400 whitespace-nowrap">
                      {lead.location || '—'}
                    </td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      <StatusBadge status={lead.status || 'New'} />
                    </td>
                    <td className="py-2 px-3 text-gray-700 dark:text-golden-300 whitespace-nowrap">
                      {lead.assignedToName || 'Unassigned'}
                    </td>
                    <td className="py-2 px-3 text-gray-500 dark:text-golden-500 whitespace-nowrap">
                      {lead.lastActivity || '—'}
                    </td>
                    <td
                      className="py-2 px-3 text-right whitespace-nowrap"
                      onClick={e => e.stopPropagation()}
                    >
                      <div className="inline-flex items-center gap-1.5">
                        {onCallLead && (
                          <button
                            type="button"
                            onClick={() => onCallLead(lead)}
                            className="px-2 py-1 rounded bg-[#2D4351] text-white hover:bg-[#20313C] font-semibold text-[11px] inline-flex items-center gap-1 transition-colors shadow-sm"
                            title="Call Lead"
                          >
                            <Phone className="w-3 h-3" />
                            Call
                          </button>
                        )}
                        {onEmailLead && (
                          <button
                            type="button"
                            onClick={() => onEmailLead(lead)}
                            className="px-2 py-1 rounded bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 font-semibold text-[11px] inline-flex items-center gap-1 transition-colors shadow-sm"
                            title="Email Lead"
                          >
                            <Mail className="w-3 h-3 text-blue-600" />
                            Email
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="p-3 border-t border-[#E5E7EB] dark:border-gray-800 flex items-center justify-between text-xs text-gray-600 dark:text-golden-400 bg-white dark:bg-black">
        <span>
          Showing {(currentPage - 1) * pageSize + 1} to{' '}
          {Math.min(currentPage * pageSize, filteredLeads.length)} of{' '}
          {filteredLeads.length} leads
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="p-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="px-2 font-medium">
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="p-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
