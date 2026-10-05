import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Sparkles, ArrowRight, CheckCircle2, Lock, User, AlertCircle, Loader2 } from 'lucide-react';
import { InteractiveBackground } from '../components/common/InteractiveBackground';

interface LoginProps {
  onLoginSuccess: () => void;
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please provide both username and password.');
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      await login(username.trim(), password);
      onLoginSuccess();
    } catch (err: any) {
      setError(err?.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] flex flex-col md:flex-row relative">
      {/* Dynamic Background FX for Login */}
      <InteractiveBackground variant="adaptive" showControls={false} />

      {/* Left Column: Product Branding & Overview */}
      <div className="md:w-1/2 bg-[#2D4351] text-white p-8 md:p-16 flex flex-col justify-between relative overflow-hidden shadow-2xl">
        <InteractiveBackground variant="dark" showControls={false} className="!absolute" />

        <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-white/5 blur-2xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-96 h-96 rounded-full bg-emerald-500/15 blur-3xl pointer-events-none" />

        <div className="relative z-10">
          <div className="flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-lg bg-white text-[#2D4351] flex items-center justify-center font-bold shadow-md">
              <Sparkles className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <span className="text-base font-bold tracking-tight block leading-none">
                DataOps AI
              </span>
              <span className="text-[10px] text-gray-300 tracking-wider uppercase block mt-1">
                Ops Intelligence Platform
              </span>
            </div>
          </div>

          <div className="space-y-4 max-w-lg">
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-white/10 text-emerald-300 border border-white/10 inline-block">
              Internal Enterprise Operations
            </span>
            <h1 className="text-3xl lg:text-4xl font-extrabold tracking-tight text-white leading-tight">
              Autonomous Intelligence & Data Pipeline Platform.
            </h1>
            <p className="text-sm text-gray-300 leading-relaxed">
              Equipped with autonomous LangGraph intelligence agents, unified data deduplication, and continuous verified lead pipelines.
            </p>
          </div>
        </div>

        {/* Feature Highlights */}
        <div className="relative z-10 my-8 space-y-3">
          {[
            'Autonomous 4-engine scraping & LangGraph agent pipeline',
            'PostgreSQL persistence with duplicate prevention',
            'Full auditability, activity telemetry & transcript inspection',
            'Knowledge base RAG integration for contextual discovery',
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2.5 text-xs text-gray-200">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>{item}</span>
            </div>
          ))}
        </div>

        <div className="relative z-10 text-xs text-gray-400">
          Secure Authentication • JWT Bearer Token Pipeline
        </div>
      </div>

      {/* Right Column: Sign In Form */}
      <div className="md:w-1/2 flex items-center justify-center p-8 md:p-16">
        <div className="w-full max-w-md space-y-6">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Sign in to your workspace</h2>
            <p className="text-xs text-[#848485] mt-1">
              Enter your enterprise credentials to access the platform
            </p>
          </div>

          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-2.5 text-xs text-rose-700">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Standard Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">
                Username
              </label>
              <div className="relative">
                <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  required
                  autoFocus
                  placeholder="e.g. admin or username"
                  className="w-full text-xs pl-9 pr-3 py-2.5 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  placeholder="••••••••••••"
                  className="w-full text-xs pl-9 pr-3 py-2.5 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 px-4 rounded-lg bg-[#2D4351] text-white text-xs font-semibold hover:bg-[#20313C] transition-colors flex items-center justify-center gap-2 shadow-sm disabled:opacity-60 cursor-pointer"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <span>Sign In to Platform</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
