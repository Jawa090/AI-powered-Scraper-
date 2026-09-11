import React from 'react';
import { Lead } from '../../types';
import { StatusBadge } from '../common/StatusBadge';
import {
  X,
  Phone,
  Mail,
  Building2,
  MapPin,
  Globe,
  Linkedin,
  Calendar,
  User,
  Clock,
  CheckCircle2,
} from 'lucide-react';

interface LeadDrawerProps {
  lead: Lead | null;
  isOpen: boolean;
  onClose: () => void;
  onCall: (lead: Lead) => void;
  onEmail: (lead: Lead) => void;
}

export const LeadDrawer: React.FC<LeadDrawerProps> = ({
  lead,
  isOpen,
  onClose,
  onCall,
  onEmail,
}) => {
  if (!isOpen || !lead) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-[1px] transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white shadow-drawer border-l border-[#E5E7EB] flex flex-col transform transition-transform duration-300">
          {/* Drawer Header */}
          <div className="p-5 border-b border-[#E5E7EB] bg-[#F8F9FA]/60">
            <div className="flex items-start justify-between">
              <div>
                <StatusBadge status={lead.status} />
                <h2 className="text-base font-bold text-gray-900 mt-2">{lead.name}</h2>
                <p className="text-xs text-gray-600 font-medium">
                  {lead.title} at <span className="text-gray-900">{lead.company}</span>
                </p>
              </div>
              <button
                onClick={onClose}
                className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Quick action buttons */}
            <div className="flex items-center gap-2 mt-4">
              <button
                onClick={() => onCall(lead)}
                className="flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold bg-[#2D4351] text-white hover:bg-[#20313C] flex items-center justify-center gap-1.5 shadow-sm transition-colors"
              >
                <Phone className="w-3.5 h-3.5" />
                <span>Call Lead</span>
              </button>
              <button
                onClick={() => onEmail(lead)}
                className="flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 flex items-center justify-center gap-1.5 shadow-sm transition-colors"
              >
                <Mail className="w-3.5 h-3.5 text-purple-600" />
                <span>Send Email</span>
              </button>
            </div>
          </div>

          {/* Drawer Content */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {/* Contact Details */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-2.5">
                Contact Information
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center gap-2.5 text-gray-700">
                  <Mail className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <a href={`mailto:${lead.email}`} className="text-blue-600 hover:underline">
                    {lead.email}
                  </a>
                </div>
                <div className="flex items-center gap-2.5 text-gray-700">
                  <Phone className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <span>{lead.phone}</span>
                </div>
                <div className="flex items-center gap-2.5 text-gray-700">
                  <MapPin className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <span>{lead.location}</span>
                </div>
                {lead.linkedin && (
                  <div className="flex items-center gap-2.5 text-gray-700">
                    <Linkedin className="w-4 h-4 text-blue-500 flex-shrink-0" />
                    <span className="text-blue-600 truncate">{lead.linkedin}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Company Details */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-2.5">
                Company Information
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Company</span>
                  <span className="font-medium text-gray-900">{lead.company}</span>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Industry</span>
                  <span className="font-medium text-gray-900">{lead.industry || 'Commercial Construction'}</span>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Company Size</span>
                  <span className="font-medium text-gray-900">{lead.companySize || '50–500'}</span>
                </div>
                {lead.website && (
                  <div className="flex items-center justify-between py-1 border-b border-gray-100">
                    <span className="text-gray-500">Website</span>
                    <a
                      href={lead.website}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline flex items-center gap-1"
                    >
                      <Globe className="w-3 h-3" />
                      Website
                    </a>
                  </div>
                )}
              </div>
            </div>

            {/* Assignment & Notes */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-2.5">
                Assignment & Operational Context
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Assigned Rep</span>
                  <span className="font-medium text-gray-900">{lead.assignedToName}</span>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Department</span>
                  <span className="font-medium text-gray-900">{lead.departmentName}</span>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-gray-100">
                  <span className="text-gray-500">Source Dataset</span>
                  <span className="font-medium text-gray-900 truncate max-w-[200px]">{lead.datasetName}</span>
                </div>
              </div>

              {lead.notes && (
                <div className="mt-3 p-3 bg-amber-50/70 border border-amber-200/80 rounded-lg text-xs text-amber-900">
                  <p className="font-semibold mb-0.5">Rep Notes:</p>
                  <p className="leading-relaxed">{lead.notes}</p>
                </div>
              )}
            </div>

            {/* Activity Timeline */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#848485] mb-2.5">
                Activity Timeline
              </h3>
              <div className="space-y-3 pl-2 border-l-2 border-gray-200">
                <div className="relative pl-3">
                  <span className="absolute -left-[19px] top-1 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
                  <p className="text-xs font-semibold text-gray-900">{lead.lastActivity}</p>
                  <p className="text-[11px] text-gray-400">Recent action logged</p>
                </div>
                <div className="relative pl-3">
                  <span className="absolute -left-[19px] top-1 w-2.5 h-2.5 rounded-full bg-gray-300 ring-2 ring-white" />
                  <p className="text-xs font-semibold text-gray-700">Lead ingested from {lead.datasetName}</p>
                  <p className="text-[11px] text-gray-400">{lead.createdAt}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
