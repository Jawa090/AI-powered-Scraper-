import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api.service';
import { AdminUser } from '../types';
import {
  Users,
  UserPlus,
  KeyRound,
  UserX,
  Shield,
  User as UserIcon,
  CheckCircle,
  AlertCircle,
  Loader2,
  Lock,
} from 'lucide-react';
import { Modal } from '../components/common/Modal';

export const AdminUsers: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create User Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', username: '', password: '' });
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Reset Password Modal
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getAdminUsers();
      setUsers(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.username || !createForm.password) return;
    setCreateLoading(true);
    setCreateError(null);
    try {
      await apiService.createAdminUser({
        name: createForm.name || createForm.username,
        username: createForm.username,
        password: createForm.password,
        role: 'user',
      });
      setIsCreateOpen(false);
      setCreateForm({ name: '', username: '', password: '' });
      fetchUsers();
    } catch (err: any) {
      setCreateError(err?.message || 'Failed to create user');
    } finally {
      setCreateLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser || !newPassword) return;
    setResetLoading(true);
    setResetError(null);
    try {
      await apiService.updateAdminUser(selectedUser.id, { password: newPassword });
      setSelectedUser(null);
      setNewPassword('');
      fetchUsers();
    } catch (err: any) {
      setResetError(err?.message || 'Failed to reset password');
    } finally {
      setResetLoading(false);
    }
  };

  const handleDisableUser = async (user: AdminUser) => {
    if (user.builtIn) return;
    if (!window.confirm(`Are you sure you want to disable user ${user.username}?`)) return;
    try {
      await apiService.disableAdminUser(user.id);
      fetchUsers();
    } catch (err: any) {
      alert(err?.message || 'Failed to disable user');
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">User Management</h1>
            <span className="text-xs bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full border border-indigo-200">
              Admin Only
            </span>
          </div>
          <p className="text-xs text-[#848485] mt-1">
            Manage system accounts, create new users, reset passwords, and audit account privileges.
          </p>
        </div>

        <button
          onClick={() => {
            setCreateError(null);
            setIsCreateOpen(true);
          }}
          className="px-3.5 py-2 rounded-lg bg-[#2D4351] hover:bg-[#20313C] text-white text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors cursor-pointer self-start sm:self-auto"
        >
          <UserPlus className="w-4 h-4" />
          <span>Create User</span>
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-2 text-xs text-rose-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Users Table */}
      <div className="bg-white border border-[#E5E7EB] rounded-xl shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#E5E7EB] bg-[#F8F9FA] text-[11px] font-bold uppercase tracking-wider text-[#848485]">
                <th className="py-3 px-4">User</th>
                <th className="py-3 px-4">Username</th>
                <th className="py-3 px-4">Role</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Source</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5E7EB]">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-gray-500">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-[#2D4351]" />
                    <span>Loading users...</span>
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-gray-500">
                    No users found.
                  </td>
                </tr>
              ) : (
                users.map(u => {
                  const isEnv = u.builtIn || u.auth_source === 'env';
                  const isActive = u.status?.toLowerCase() === 'active';

                  return (
                    <tr key={u.id} className="hover:bg-[#F8F9FA]/80 transition-colors">
                      <td className="py-3 px-4 font-semibold text-gray-900">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center font-bold text-gray-600">
                            {u.name ? u.name.charAt(0).toUpperCase() : u.username.charAt(0).toUpperCase()}
                          </div>
                          <span>{u.name || u.username}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-gray-700">
                        {u.username}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            u.role === 'admin'
                              ? 'bg-amber-50 text-amber-800 border border-amber-200'
                              : 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                          }`}
                        >
                          {u.role === 'admin' ? (
                            <Shield className="w-3 h-3 text-amber-600" />
                          ) : (
                            <UserIcon className="w-3 h-3 text-indigo-600" />
                          )}
                          {u.role}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${
                            isActive
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-gray-100 text-gray-500 border border-gray-200'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              isActive ? 'bg-emerald-500' : 'bg-gray-400'
                            }`}
                          />
                          {u.status || 'Active'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {isEnv ? (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200 inline-flex items-center gap-1">
                            <Lock className="w-3 h-3" />
                            Built-in (Read-Only)
                          </span>
                        ) : (
                          <span className="text-[10px] text-gray-500">Database</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        {isEnv ? (
                          <span className="text-[11px] text-gray-400 italic">Managed in .env</span>
                        ) : (
                          <div className="inline-flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedUser(u);
                                setNewPassword('');
                                setResetError(null);
                              }}
                              className="px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-semibold text-[11px] inline-flex items-center gap-1 transition-colors cursor-pointer"
                              title="Reset Password"
                            >
                              <KeyRound className="w-3 h-3 text-indigo-600" />
                              <span>Reset Password</span>
                            </button>
                            {isActive && (
                              <button
                                type="button"
                                onClick={() => handleDisableUser(u)}
                                className="px-2 py-1 rounded bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-semibold text-[11px] inline-flex items-center gap-1 transition-colors cursor-pointer"
                                title="Disable User"
                              >
                                <UserX className="w-3 h-3" />
                                <span>Disable</span>
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create User Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create New User"
        subtitle="Provision a new platform database user with role 'user'."
        maxWidth="md"
      >
        <form onSubmit={handleCreateUser} className="space-y-4">
          {createError && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{createError}</span>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              Full Name (Optional)
            </label>
            <input
              type="text"
              value={createForm.name}
              onChange={e => setCreateForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g. Jane Doe"
              className="w-full text-xs px-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              Username <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              required
              value={createForm.username}
              onChange={e => setCreateForm(prev => ({ ...prev, username: e.target.value }))}
              placeholder="e.g. janedoe"
              className="w-full text-xs px-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              Password <span className="text-rose-500">*</span>
            </label>
            <input
              type="password"
              required
              value={createForm.password}
              onChange={e => setCreateForm(prev => ({ ...prev, password: e.target.value }))}
              placeholder="Minimum 8 characters"
              className="w-full text-xs px-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsCreateOpen(false)}
              className="px-3.5 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-100 rounded-lg transition-colors border border-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createLoading}
              className="px-4 py-2 text-xs font-semibold bg-[#2D4351] hover:bg-[#20313C] text-white rounded-lg transition-colors shadow-sm disabled:opacity-60 flex items-center gap-1.5"
            >
              {createLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Create Account</span>
            </button>
          </div>
        </form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal
        isOpen={Boolean(selectedUser)}
        onClose={() => setSelectedUser(null)}
        title={`Reset Password for ${selectedUser?.username}`}
        subtitle="Set a new secure password for this user account."
        maxWidth="md"
      >
        <form onSubmit={handleResetPassword} className="space-y-4">
          {resetError && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{resetError}</span>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-gray-700 block mb-1">
              New Password <span className="text-rose-500">*</span>
            </label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="Enter new password"
              className="w-full text-xs px-3 py-2 bg-white border border-[#E5E7EB] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351]"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setSelectedUser(null)}
              className="px-3.5 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-100 rounded-lg transition-colors border border-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={resetLoading}
              className="px-4 py-2 text-xs font-semibold bg-[#2D4351] hover:bg-[#20313C] text-white rounded-lg transition-colors shadow-sm disabled:opacity-60 flex items-center gap-1.5"
            >
              {resetLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Update Password</span>
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
