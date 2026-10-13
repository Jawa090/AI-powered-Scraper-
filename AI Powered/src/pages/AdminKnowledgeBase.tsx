import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api.service';
import { RagStatus, RagDocument } from '../types';
import {
  Database,
  Upload,
  Trash2,
  FileText,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Loader2,
  Layers,
  Cpu,
  Hash,
} from 'lucide-react';
import { Modal } from '../components/common/Modal';

export const AdminKnowledgeBase: React.FC = () => {
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusLoading, setStatusLoading] = useState(false);

  // Upload Modal
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [docTitle, setDocTitle] = useState('');
  const [docContent, setDocContent] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const fetchStatusAndDocs = async () => {
    setLoading(true);
    try {
      const [ragStatus, ragDocs] = await Promise.all([
        apiService.getRagStatus(),
        apiService.getRagDocuments(),
      ]);
      setStatus(ragStatus);
      setDocuments(ragDocs);
    } catch (err) {
      console.warn('Failed to load KB data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatusAndDocs();
  }, []);

  const handleRefreshStatus = async () => {
    setStatusLoading(true);
    try {
      const ragStatus = await apiService.getRagStatus();
      setStatus(ragStatus);
    } finally {
      setStatusLoading(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!docContent.trim()) return;

    setUploading(true);
    setUploadError(null);
    try {
      const success = await apiService.uploadRagDocument(docContent, docTitle || 'Knowledge Base Note');
      if (success) {
        setIsUploadOpen(false);
        setDocTitle('');
        setDocContent('');
        fetchStatusAndDocs();
      } else {
        setUploadError('Failed to upload document to Knowledge Base');
      }
    } catch (err: any) {
      setUploadError(err?.message || 'Upload error');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!window.confirm('Are you sure you want to delete this document from the knowledge base?')) return;
    try {
      await apiService.deleteRagDocument(docId);
      fetchStatusAndDocs();
    } catch (err: any) {
      alert(err?.message || 'Failed to delete document');
    }
  };

  const isReady = status?.available || status?.state === 'ready';

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">Knowledge Base (RAG)</h1>
            <span className="text-xs bg-white text-blue-600 font-semibold px-2 py-0.5 rounded-full border border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800">
              Admin Only
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-1">
            Status, documents, and vector index configuration via the RAG microservice.
          </p>
        </div>

        <button
          onClick={() => {
            setUploadError(null);
            setIsUploadOpen(true);
          }}
          className="px-3.5 py-2 rounded-lg bg-[#2D4351] hover:bg-[#20313C] text-white text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors cursor-pointer self-start sm:self-auto"
        >
          <Upload className="w-4 h-4" />
          <span>Upload Text Document</span>
        </button>
      </div>

      {/* RAG Telemetry Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Status Card */}
        <div className="p-4 bg-white border border-[#E5E7EB] rounded-xl shadow-card flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#848485] text-xs">
            <span className="font-semibold uppercase tracking-wider text-[10px]">Index State</span>
            <button
              onClick={handleRefreshStatus}
              title="Refresh RAG status"
              className="p-1 hover:bg-gray-100 rounded text-gray-500"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${statusLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                isReady ? 'bg-green-600 dark:bg-green-500 animate-pulse' : 'bg-blue-600 dark:bg-blue-500'
              }`}
            />
            <span className="text-base font-bold text-gray-900 capitalize">
              {status?.state || 'Checking...'}
            </span>
          </div>
          <p className="text-[11px] text-gray-500 mt-1">
            {status?.message || (isReady ? 'RAG vector index ready' : 'Service offline or not configured')}
          </p>
        </div>

        {/* Documents Indexed */}
        <div className="p-4 bg-white border border-[#E5E7EB] rounded-xl shadow-card">
          <div className="flex items-center justify-between text-[#848485] text-xs">
            <span className="font-semibold uppercase tracking-wider text-[10px]">Documents</span>
            <FileText className="w-4 h-4 text-blue-500" />
          </div>
          <div className="mt-2 text-2xl font-extrabold text-gray-900">
            {status?.documents ?? documents.length}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Ingested context docs</p>
        </div>

        {/* Chunks */}
        <div className="p-4 bg-white border border-[#E5E7EB] rounded-xl shadow-card">
          <div className="flex items-center justify-between text-[#848485] text-xs">
            <span className="font-semibold uppercase tracking-wider text-[10px]">Vector Chunks</span>
            <Layers className="w-4 h-4 text-blue-500" />
          </div>
          <div className="mt-2 text-2xl font-extrabold text-gray-900">
            {status?.chunks ?? 0}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Embedded chunks in pgvector</p>
        </div>

        {/* Embedding Model */}
        <div className="p-4 bg-white border border-[#E5E7EB] rounded-xl shadow-card">
          <div className="flex items-center justify-between text-[#848485] text-xs">
            <span className="font-semibold uppercase tracking-wider text-[10px]">Embedding Model</span>
            <Cpu className="w-4 h-4 text-green-500" />
          </div>
          <div className="mt-2 text-sm font-bold text-gray-900 truncate">
            {status?.embeddingModel || 'text-embedding-004'}
          </div>
          <p className="text-[11px] text-gray-500 mt-1">
            Dim: {status?.dim || 768} • API: {status?.version || 'v1'}
          </p>
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <div className="p-4 border-b border-[#E5E7EB] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Indexed Knowledge Documents</h3>
          <span className="text-xs text-gray-500">{documents.length} document(s)</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[11px] font-bold uppercase tracking-wider text-[#848485]">
                <th className="py-3 px-4">Document Title</th>
                <th className="py-3 px-4">Document ID</th>
                <th className="py-3 px-4">Chunks</th>
                <th className="py-3 px-4">Created At</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5E7EB]">
              {loading ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-gray-500">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-[#2D4351]" />
                    <span>Loading knowledge base documents...</span>
                  </td>
                </tr>
              ) : documents.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-gray-500">
                    No documents found in knowledge base. Upload text to begin.
                  </td>
                </tr>
              ) : (
                documents.map(doc => (
                  <tr key={doc.id} className="hover:bg-[#F8F9FA]/80 transition-colors">
                    <td className="py-3 px-4 font-semibold text-gray-900">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-blue-600 flex-shrink-0" />
                        <span className="truncate max-w-sm">{doc.title || 'Untitled Document'}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-gray-500">
                      {doc.id}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-gray-700">
                      {doc.chunksCount ?? '—'}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-[11px] whitespace-nowrap">
                      {doc.createdAt ? new Date(doc.createdAt).toLocaleDateString() : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        type="button"
                        onClick={() => handleDelete(doc.id)}
                        className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-500 dark:hover:bg-red-900/30 transition-colors"
                        title="Delete Document"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Upload Document Modal */}
      <Modal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        title="Upload Knowledge Document"
        subtitle="Ingest plain text or markdown documentation into the vector retrieval database."
        maxWidth="lg"
      >
        <form onSubmit={handleUpload} className="space-y-4">
          {uploadError && (
            <div className="p-3 bg-white text-red-600 border border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 rounded-lg text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              Document Title
            </label>
            <input
              type="text"
              value={docTitle}
              onChange={e => setDocTitle(e.target.value)}
              placeholder="e.g. Dallas Bonfire Scraper Specifications"
              className="w-full text-xs px-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              Content (Text / Markdown) <span className="text-red-500">*</span>
            </label>
            <textarea
              required
              rows={8}
              value={docContent}
              onChange={e => setDocContent(e.target.value)}
              placeholder="Paste document text here to be chunked and embedded..."
              className="w-full text-xs px-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351] font-mono leading-relaxed"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsUploadOpen(false)}
              className="px-3.5 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-100 rounded-lg transition-colors border border-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={uploading || !docContent.trim()}
              className="px-4 py-2 text-xs font-semibold bg-[#2D4351] hover:bg-[#20313C] text-white rounded-lg transition-colors shadow-sm disabled:opacity-60 flex items-center gap-1.5"
            >
              {uploading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Ingest Document</span>
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
