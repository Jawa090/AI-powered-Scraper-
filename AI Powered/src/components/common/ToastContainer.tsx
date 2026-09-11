import React from 'react';
import { useDataOps } from '../../context/DataOpsContext';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useDataOps();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map(toast => {
        const Icon =
          toast.type === 'success'
            ? CheckCircle2
            : toast.type === 'error'
            ? AlertCircle
            : toast.type === 'warning'
            ? AlertTriangle
            : Info;

        const iconColor =
          toast.type === 'success'
            ? 'text-emerald-500'
            : toast.type === 'error'
            ? 'text-rose-500'
            : toast.type === 'warning'
            ? 'text-amber-500'
            : 'text-blue-500';

        return (
          <div
            key={toast.id}
            className="pointer-events-auto bg-white border border-[#E5E7EB] shadow-dropdown rounded-lg p-3.5 flex items-start gap-3 transition-all transform animate-in slide-in-from-bottom-2"
          >
            <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5 ${iconColor}`} />
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-gray-900">{toast.title}</h4>
              <p className="text-xs text-gray-600 mt-0.5 leading-relaxed">{toast.message}</p>
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-gray-400 hover:text-gray-600 p-0.5 rounded"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
