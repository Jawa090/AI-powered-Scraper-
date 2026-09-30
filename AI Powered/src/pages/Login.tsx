import React, { useState } from 'react';
import { useDataOps } from '../context/DataOpsContext';
import { Sparkles, Shield, ArrowRight, CheckCircle2, Lock, Mail } from 'lucide-react';
import { UserRole } from '../types';
import { InteractiveBackground } from '../components/common/InteractiveBackground';

interface LoginProps {
  onLoginSuccess: () => void;
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const { switchRole, allUsers } = useDataOps();
  const [email, setEmail] = useState('ahmed.khan@company.internal');
  const [password, setPassword] = useState('••••••••••••');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLoginSuccess();
  };

  const handleQuickRole = (role: UserRole) => {
    switchRole(role);
    onLoginSuccess();
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] flex flex-col md:flex-row relative">
      {/* Dynamic Background FX for Login */}
      <InteractiveBackground variant="adaptive" showControls={false} />

      {/* Left Column: Product Branding & Overview */}
      <div className="md:w-1/2 bg-[#2D4351] text-white p-8 md:p-16 flex flex-col justify-between relative overflow-hidden shadow-2xl">
        {/* Dedicated Dark Mode Interactive Particle Canvas */}
        <InteractiveBackground variant="dark" showControls={false} className="!absolute" />
        
        {/* Subtle geometric pattern */}
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
              Autonomous Departmental Data Intelligence.
            </h1>
            <p className="text-sm text-gray-300 leading-relaxed">
              Every department equipped with dedicated AI agents for continuous lead discovery, live MX email verification, and closed-loop calling workflows.
            </p>
          </div>
        </div>

        {/* Feature Highlights */}
        <div className="relative z-10 my-8 space-y-3">
          {[
            'Department-specific autonomous AI intelligence agents',
            'Live phone dialer & MX email deliverability validation',
            'Zero manual CSV downloads: Reps work directly in-platform',
            'Centralized management telemetry & conversion funnel',
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-2.5 text-xs text-gray-200">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>{item}</span>
            </div>
          ))}
        </div>

        <div className="relative z-10 text-xs text-gray-400">
          Secure Single Sign-On • SOC2 Type II Certified Pipeline
        </div>
      </div>

      {/* Right Column: Sign In Form & Quick Personas */}
      <div className="md:w-1/2 flex items-center justify-center p-8 md:p-16">
        <div className="w-full max-w-md space-y-6">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Sign in to your workspace</h2>
            <p className="text-xs text-[#848485] mt-1">
              Enter enterprise credentials or select a simulated persona
            </p>
          </div>

          {/* Quick Persona Launchers */}
          <div className="p-3.5 bg-white border border-[#E5E7EB] rounded-xl shadow-card space-y-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#848485] block">
              1-Click Demo Persona Login:
            </span>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleQuickRole('sales')}
                className="p-2.5 rounded-lg border border-gray-200 hover:border-[#2D4351] hover:bg-gray-50 text-left transition-all group"
              >
                <span className="text-xs font-semibold text-gray-900 block group-hover:text-[#2D4351]">
                  Ahmed Khan
                </span>
                <span className="text-[10px] text-gray-500 block">Sales 1 Specialist</span>
              </button>
              <button
                type="button"
                onClick={() => handleQuickRole('email')}
                className="p-2.5 rounded-lg border border-gray-200 hover:border-[#2D4351] hover:bg-gray-50 text-left transition-all group"
              >
                <span className="text-xs font-semibold text-gray-900 block group-hover:text-[#2D4351]">
                  Sara Jenkins
                </span>
                <span className="text-[10px] text-gray-500 block">Email Marketing Lead</span>
              </button>
              <button
                type="button"
                onClick={() => handleQuickRole('manager')}
                className="p-2.5 rounded-lg border border-gray-200 hover:border-[#2D4351] hover:bg-gray-50 text-left transition-all group"
              >
                <span className="text-xs font-semibold text-gray-900 block group-hover:text-[#2D4351]">
                  Marcus Vance
                </span>
                <span className="text-[10px] text-gray-500 block">Revenue Manager</span>
              </button>
              <button
                type="button"
                onClick={() => handleQuickRole('admin')}
                className="p-2.5 rounded-lg border border-gray-200 hover:border-[#2D4351] hover:bg-gray-50 text-left transition-all group"
              >
                <span className="text-xs font-semibold text-gray-900 block group-hover:text-[#2D4351]">
                  Elena Rostova
                </span>
                <span className="text-[10px] text-gray-500 block">Enterprise Admin</span>
              </button>
            </div>
          </div>

          {/* Standard Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-gray-700 block mb-1">
                Corporate Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  placeholder="employee@company.internal"
                  className="w-full text-xs pl-9 pr-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
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
                  className="w-full text-xs pl-9 pr-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 px-4 rounded-lg bg-[#2D4351] text-white text-xs font-semibold hover:bg-[#20313C] transition-colors flex items-center justify-center gap-2 shadow-sm"
            >
              <span>Sign In to Platform</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
