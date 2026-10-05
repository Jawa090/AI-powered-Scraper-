import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api.service';
import { AdminRequestItem, AdminRequestDetail } from '../types';
import {
  ActivitySquare,
  Filter,
  Download,
  Search,
  Eye,
  ChevronLeft,
  ChevronRight,
  Database,
  Bot,
  User,
  CheckCircle,
  AlertCircle,
  Loader2,
  Calendar,
  X,
  FileText,
} from 'lucide-react';
import { Modal } from '../components/common/Modal';

export const AdminActivity: React.FC = () => {
  const [requests, setRequests] = useState<AdminRequestItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [loading, setLoading] = useState(true);

  // Filters
  const [userIdFilter, setUserIdFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  // Detail Modal
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminRequestDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const fetchRequests = async () => {
    setLoading(true);
    try {
      const res = await apiService.getAdminRequests({
        userId: userIdFilter || undefined,
        decision: decisionFilter || undefined,
        source: sourceFilter || undefined,
        from: fromDate || undefined,
        to: toDate || undefined,
        page,
        pageSize,
      });
      setRequests(res.items);
      setTotal(res.total);
    } catch (err) {
      console.warn('Failed to load admin requests:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequests();
  }, [page, decisionFilter, sourceFilter]);

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchRequests();
  };

  const handleOpenDetail = async (requestId: string) => {
    setSelectedRequestId(requestId);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const data = await apiService.getAdminRequestDetail(requestId);
      setDetail(data);
    } catch (err: any) {
      setDetailError(err?.message || 'Failed to fetch request detail');
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  const exportUrl = apiService.getAdminRequestsExportUrl({
    userId: userIdFilter || undefined,
    decision: decisionFilter || undefined,
    from: fromDate || undefined,
    to: toDate || undefined,
  });

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">Activity Telemetry</h1>
            <span className="text-xs bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full border border-indigo-200">
              Admin Only
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-1">
            Query transcripts, LLM decisions, RAG hits, tool execution traces, and rows served.
          </p>
        </div>

        <a
          href={exportUrl}
          download="requests_export.csv"
          className="px-3.5 py-2 rounded-lg bg-white border border-[#E5E7EB] hover:bg-gray-50 text-gray-700 text-xs font-semibold flex items-center gap-2 shadow-subtle transition-colors cursor-pointer self-start sm:self-auto"
        >
          <Download className="w-4 h-4 text-gray-500" />
          <span>Export CSV</span>
        </a>
      </div>

      {/* Filter Bar */}
      <form
        onSubmit={handleApplyFilters}
        className="bg-white border border-[#E5E7EB] rounded-xl p-4 shadow-card grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 items-end"
      >
        <div>
          <label className="text-[11px] font-semibold text-gray-600 block mb-1">Decision</label>
          <select
            value={decisionFilter}
            onChange={e => setDecisionFilter(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          >
            <option value="">All Decisions</option>
            <option value="USE_DATABASE">USE_DATABASE</option>
            <option value="NEED_FETCH">NEED_FETCH</option>
            <option value="PARTIAL">PARTIAL</option>
            <option value="NEED_CLARIFICATION">NEED_CLARIFICATION</option>
          </select>
        </div>

        <div>
          <label className="text-[11px] font-semibold text-gray-600 block mb-1">Source Scraper</label>
          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          >
            <option value="">All Sources</option>
            <option value="bonfire">Bonfire</option>
            <option value="dasny">DASNY</option>
            <option value="jwiz">JWiz</option>
            <option value="nyscr">NYSCR</option>
          </select>
        </div>

        <div>
          <label className="text-[11px] font-semibold text-gray-600 block mb-1">From Date</label>
          <input
            type="date"
            value={fromDate}
            onChange={e => setFromDate(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

        <div>
          <label className="text-[11px] font-semibold text-gray-600 block mb-1">To Date</label>
          <input
            type="date"
            value={toDate}
            onChange={e => setToDate(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

        <div>
          <label className="text-[11px] font-semibold text-gray-600 block mb-1">User ID</label>
          <input
            type="text"
            value={userIdFilter}
            onChange={e => setUserIdFilter(e.target.value)}
            placeholder="Filter by user id"
            className="w-full text-xs px-2.5 py-1.5 bg-[#F8F9FA] border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            type="submit"
            className="w-full py-1.5 px-3 bg-[#2D4351] hover:bg-[#20313C] text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer shadow-sm"
          >
            <Filter className="w-3.5 h-3.5" />
            <span>Apply</span>
          </button>
          {(decisionFilter || sourceFilter || fromDate || toDate || userIdFilter) && (
            <button
              type="button"
              onClick={() => {
                setDecisionFilter('');
                setSourceFilter('');
                setFromDate('');
                setToDate('');
                setUserIdFilter('');
              }}
              className="py-1.5 px-2 bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-lg text-xs transition-colors"
              title="Clear filters"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </form>

      {/* Requests Table */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[11px] font-bold uppercase tracking-wider text-[#848485]">
                <th className="py-3 px-4">Request ID</th>
                <th className="py-3 px-4">User</th>
                <th className="py-3 px-4">Query</th>
                <th className="py-3 px-4">Decision</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Records</th>
                <th className="py-3 px-4">Created At</th>
                <th className="py-3 px-4 text-right">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5E7EB]">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-gray-500">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-[#2D4351]" />
                    <span>Loading activity requests...</span>
                  </td>
                </tr>
              ) : requests.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-gray-500">
                    No matching requests found.
                  </td>
                </tr>
              ) : (
                requests.map(q => (
                  <tr
                    key={q.id}
                    onClick={() => handleOpenDetail(q.id)}
                    className="hover:bg-[#F8F9FA]/80 transition-colors cursor-pointer"
                  >
                    <td className="py-3 px-4 font-mono text-[11px] text-gray-500">
                      {q.id.length > 12 ? `${q.id.substring(0, 10)}...` : q.id}
                    </td>
                    <td className="py-3 px-4 font-medium text-gray-900">
                      {q.userName || q.userId}
                    </td>
                    <td className="py-3 px-4 text-gray-700 max-w-xs truncate">
                      {q.queryText || '—'}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase ${
                          q.decision === 'USE_DATABASE'
                            ? 'bg-blue-50 text-blue-700 border border-blue-200'
                            : q.decision?.includes('FETCH')
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-gray-100 text-gray-700 border border-gray-200'
                        }`}
                      >
                        {q.decision || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="text-[11px] font-semibold text-gray-700">
                        {q.status || 'answered'}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-gray-600">
                      {q.recordsReturned ?? 0}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-[11px] whitespace-nowrap">
                      {q.createdAt ? new Date(q.createdAt).toLocaleString() : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        type="button"
                        onClick={e => {
                          e.stopPropagation();
                          handleOpenDetail(q.id);
                        }}
                        className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100"
                        title="View details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="p-3 border-t border-[#E5E7EB] bg-white flex items-center justify-between text-xs text-gray-600">
          <span>
            Total: <strong>{total}</strong> requests
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded border border-[#E5E7EB] hover:bg-gray-50 disabled:opacity-40"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span>
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-1.5 rounded border border-[#E5E7EB] hover:bg-gray-50 disabled:opacity-40"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Request Detail Modal */}
      <Modal
        isOpen={Boolean(selectedRequestId)}
        onClose={() => {
          setSelectedRequestId(null);
          setDetail(null);
        }}
        title={`Request Detail: ${selectedRequestId?.substring(0, 16)}...`}
        subtitle="Complete audit trail, transcripts, tool trace, and served rows."
        maxWidth="2xl"
      >
        {detailLoading ? (
          <div className="py-16 text-center text-gray-500">
            <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-[#2D4351]" />
            <span>Loading request telemetry...</span>
          </div>
        ) : detailError ? (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            <span>{detailError}</span>
          </div>
        ) : detail ? (
          <div className="space-y-5 text-xs max-h-[75vh] overflow-y-auto pr-1">
            {/* Overview Card */}
            <div className="p-4 bg-gray-50 rounded-xl border border-gray-200 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase font-bold tracking-wider text-gray-500">
                  User Query
                </span>
                <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-white border border-gray-300 font-bold">
                  {detail.request.decision}
                </span>
              </div>
              <p className="text-sm font-semibold text-gray-900">
                "{detail.request.queryText}"
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-gray-200 text-[11px]">
                <div>
                  <span className="text-gray-500 block">Status:</span>
                  <span className="font-semibold text-gray-800">{detail.request.status}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Rows Served:</span>
                  <span className="font-semibold text-gray-800">{detail.request.recordsReturned || 0}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">New Records:</span>
                  <span className="font-semibold text-gray-800">{detail.request.recordsNew || 0}</span>
                </div>
                <div>
                  <span className="text-gray-500 block">Created:</span>
                  <span className="font-semibold text-gray-800">
                    {detail.request.createdAt ? new Date(detail.request.createdAt).toLocaleTimeString() : '—'}
                  </span>
                </div>
              </div>
            </div>

            {/* Related Job (if any) */}
            {detail.job && (
              <div className="p-4 bg-indigo-50/50 rounded-xl border border-indigo-200 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-700">
                    Associated Scraper Job
                  </span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-mono">
                    {detail.job.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px]">
                  <span>Script: <strong>{detail.job.scriptId}</strong></span>
                  <span>Found: <strong>{detail.job.recordsFound}</strong></span>
                  <span>Verified: <strong>{detail.job.verifiedCount}</strong></span>
                  <span>Duplicates Prevented: <strong>{detail.job.duplicatesCount}</strong></span>
                </div>
              </div>
            )}

            {/* Transcript */}
            <div className="space-y-2">
              <h4 className="text-[11px] uppercase font-bold tracking-wider text-gray-600 flex items-center gap-1.5">
                <Bot className="w-3.5 h-3.5 text-indigo-600" />
                <span>Conversation Transcript ({detail.transcript?.length || 0} messages)</span>
              </h4>
              <div className="space-y-2 max-h-56 overflow-y-auto border border-gray-200 rounded-lg p-3 bg-gray-50/50">
                {(!detail.transcript || detail.transcript.length === 0) ? (
                  <p className="text-gray-400 italic text-[11px]">No transcript recorded for this session.</p>
                ) : (
                  detail.transcript.map(msg => (
                    <div
                      key={msg.id}
                      className={`p-2.5 rounded-lg border text-xs ${
                        msg.sender === 'user'
                          ? 'bg-white border-gray-200 text-gray-900 ml-4'
                          : 'bg-indigo-50/50 border-indigo-100 text-gray-900 mr-4'
                      }`}
                    >
                      <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                        <span className="font-bold uppercase">{msg.sender}</span>
                        <span>{msg.createdAt ? new Date(msg.createdAt).toLocaleTimeString() : ''}</span>
                      </div>
                      <p className="whitespace-pre-wrap">{msg.text}</p>
                      {msg.toolTrace && (
                        <div className="mt-2 p-2 bg-gray-900 text-emerald-400 font-mono text-[10px] rounded overflow-x-auto">
                          <span className="text-gray-400 block mb-0.5">Tool Trace:</span>
                          <pre>{JSON.stringify(msg.toolTrace, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Rows Served */}
            <div className="space-y-2">
              <h4 className="text-[11px] uppercase font-bold tracking-wider text-gray-600 flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-emerald-600" />
                <span>Exact Rows Served ({detail.rowsServed?.length || 0})</span>
              </h4>
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                {(!detail.rowsServed || detail.rowsServed.length === 0) ? (
                  <div className="p-3 text-center text-gray-400 italic text-[11px]">
                    No specific rows served recorded.
                  </div>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead className="bg-gray-100 text-[10px] font-bold text-gray-600 uppercase border-b border-gray-200">
                      <tr>
                        <th className="py-2 px-3">Rank</th>
                        <th className="py-2 px-3">Company</th>
                        <th className="py-2 px-3">Contact</th>
                        <th className="py-2 px-3">Title</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 bg-white">
                      {detail.rowsServed.map(row => (
                        <tr key={row.leadId}>
                          <td className="py-1.5 px-3 font-mono text-[11px] text-gray-500">#{row.rank}</td>
                          <td className="py-1.5 px-3 font-semibold text-gray-900">{row.company || '—'}</td>
                          <td className="py-1.5 px-3 text-gray-700">{row.contact || '—'}</td>
                          <td className="py-1.5 px-3 text-gray-600">{row.title || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
};
