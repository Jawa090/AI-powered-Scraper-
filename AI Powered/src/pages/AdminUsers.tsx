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
  Eye,
  EyeOff,
} from 'lucide-react';
import { Modal } from '../components/common/Modal';

export const AdminUsers: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create User Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', email: '', username: '', password: '' });
  const [showCreatePassword, setShowCreatePassword] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Reset Password Modal
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [emailUser, setEmailUser] = useState<AdminUser | null>(null);
  const [editEmail, setEditEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [emailSaving, setEmailSaving] = useState(false);
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
        email: createForm.email,
        password: createForm.password,
        role: 'user',
      });
      setIsCreateOpen(false);
      setCreateForm({ name: '', email: '', username: '', password: '' });
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
            <h1 className="text-xl font-bold text-gray-900 dark:text-golden-500 tracking-tight">User Management</h1>
            <span className="text-xs bg-white text-blue-600 font-semibold px-2 py-0.5 rounded-full border border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800">
              Admin Only
            </span>
          </div>
          <p className="text-xs text-[#848485] dark:text-golden-600 mt-1">
            Manage system accounts, create new users, reset passwords, and audit account privileges.
          </p>
        </div>

        <button
          onClick={() => {
            setCreateError(null);
            setIsCreateOpen(true);
          }}
          className="px-3.5 py-2 rounded-lg bg-[#2D4351] dark:bg-golden-500 hover:bg-[#20313C] dark:hover:bg-golden-600 text-white dark:text-black text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors cursor-pointer self-start sm:self-auto"
        >
          <UserPlus className="w-4 h-4" />
          <span>Create User</span>
        </button>
      </div>

      {error && (
        <div className="p-3 bg-white text-red-600 border border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 rounded-lg flex items-center gap-2 text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Users Table */}
      <div className="bg-white dark:bg-black border border-[#E5E7EB] dark:border-gray-800 rounded-xl shadow-card overflow-hidden transition-colors">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#E5E7EB] dark:border-gray-800 bg-[#F8F9FA] dark:bg-gray-900 text-[11px] font-bold uppercase tracking-wider text-[#848485] dark:text-golden-600">
                <th className="py-3 px-4">User</th>
                <th className="py-3 px-4">Username</th>
                <th className="py-3 px-4">Role</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Source</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E5E7EB] dark:divide-gray-800">
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
                    <tr key={u.id} className="hover:bg-[#F8F9FA]/80 dark:hover:bg-gray-800/50 transition-colors">
                      <td className="py-3 px-4 font-semibold text-gray-900 dark:text-golden-100">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center font-bold text-gray-600">
                            {u.name ? u.name.charAt(0).toUpperCase() : u.username.charAt(0).toUpperCase()}
                          </div>
                          <span>{u.name || u.username}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-gray-700 dark:text-golden-300">
                        {u.username}<div className="text-gray-500">{u.email || 'Email not set'}</div>
                        {!u.builtIn && <button type="button" className="text-blue-600 underline mt-1"
                          onClick={() => { setEmailUser(u); setEditEmail(u.email || ''); setEmailError(''); }}>Edit email</button>}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase border bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800`}
                        >
                          {u.role === 'admin' ? (
                            <Shield className="w-3 h-3 text-blue-600 dark:text-blue-500" />
                          ) : (
                            <UserIcon className="w-3 h-3 text-blue-600 dark:text-blue-500" />
                          )}
                          {u.role}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border ${
                            isActive
                              ? 'bg-white text-green-600 border-green-200 dark:bg-black dark:text-green-500 dark:border-green-800'
                              : 'bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              isActive ? 'bg-green-600 dark:bg-green-500' : 'bg-blue-600 dark:bg-blue-500'
                            }`}
                          />
                          {u.status || 'Active'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {isEnv ? (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-white text-blue-600 border-blue-200 dark:bg-black dark:text-blue-500 dark:border-blue-800 border inline-flex items-center gap-1">
                            <Lock className="w-3 h-3" />
                            Protected administrator
                          </span>
                        ) : (
                          <span className="text-[10px] text-gray-500">Database</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        {isEnv ? (
                          <span className="text-[11px] text-gray-400 italic">Protected administrator</span>
                        ) : (
                          <div className="inline-flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedUser(u);
                                setNewPassword('');
                                setResetError(null);
                              }}
                              className="px-2 py-1 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-golden-300 font-semibold text-[11px] inline-flex items-center gap-1 transition-colors cursor-pointer"
                              title="Reset Password"
                            >
                              <KeyRound className="w-3 h-3 text-blue-600" />
                              <span>Reset Password</span>
                            </button>
                            {isActive && (
                              <button
                                type="button"
                                onClick={() => handleDisableUser(u)}
                                className="px-2 py-1 rounded bg-white text-red-600 border border-red-200 hover:bg-red-50 dark:bg-black dark:text-red-500 dark:border-red-800 dark:hover:bg-red-900/30 font-semibold text-[11px] inline-flex items-center gap-1 transition-colors cursor-pointer"
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
            <div className="p-3 bg-white text-red-600 border border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 rounded-lg text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{createError}</span>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-gray-700 dark:text-golden-400 block mb-1">
              Full Name (Optional)
            </label>
            <input
              type="text"
              value={createForm.name}
              onChange={e => setCreateForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g. Jane Doe"
              className="w-full text-xs px-3 py-2 bg-white dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 dark:text-golden-100 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-700 dark:text-golden-400 block mb-1">Email *</label>
            <input type="email" required value={createForm.email}
              onChange={e => setCreateForm(prev => ({ ...prev, email: e.target.value }))}
              className="w-full text-xs px-3 py-2 bg-white dark:bg-gray-900 border dark:border-gray-700 dark:text-golden-100 rounded-lg" />
          </div>
          <div>
            <label className="text-xs font-semibold text-gray-700 dark:text-golden-400 block mb-1">
              Username <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={createForm.username}
              onChange={e => setCreateForm(prev => ({ ...prev, username: e.target.value }))}
              placeholder="e.g. janedoe"
              className="w-full text-xs px-3 py-2 bg-white dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 dark:text-golden-100 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-700 dark:text-golden-400 block mb-1">
              Password <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <input
                type={showCreatePassword ? "text" : "password"}
                required
                value={createForm.password}
                onChange={e => setCreateForm(prev => ({ ...prev, password: e.target.value }))}
                placeholder="Minimum 8 characters"
                className="w-full text-xs pl-3 pr-10 py-2 bg-white dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 dark:text-golden-100 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
              />
              <button
                type="button"
                onClick={() => setShowCreatePassword(!showCreatePassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 focus:outline-none"
              >
                {showCreatePassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
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

      <Modal isOpen={Boolean(emailUser)} onClose={() => setEmailUser(null)} title="Update user email" maxWidth="md">
        <form className="space-y-4" onSubmit={async e => {
          e.preventDefault(); if (!emailUser) return;
          setEmailSaving(true); setEmailError('');
          try { await apiService.updateAdminUser(emailUser.id, { email: editEmail }); setEmailUser(null); await fetchUsers(); }
          catch (error: any) { setEmailError(error.message || 'Could not update email'); }
          finally { setEmailSaving(false); }
        }}>
          <label className="block text-sm">Email for {emailUser?.username}
            <input required type="email" value={editEmail} onChange={e => setEditEmail(e.target.value)}
              className="block w-full mt-2 border rounded p-2 dark:bg-gray-900" />
          </label>
          {emailError && <p className="text-red-600 text-sm">{emailError}</p>}
          <button disabled={emailSaving} className="rounded px-4 py-2 bg-blue-600 text-white">{emailSaving ? 'Saving...' : 'Save email'}</button>
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
            <div className="p-3 bg-white text-red-600 border border-red-200 dark:bg-black dark:text-red-500 dark:border-red-800 rounded-lg text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{resetError}</span>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-gray-700 dark:text-golden-400 block mb-1">
              New Password <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="Enter new password"
              className="w-full text-xs px-3 py-2 bg-white dark:bg-gray-900 border border-[#E5E7EB] dark:border-gray-700 dark:text-golden-100 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#2D4351] dark:focus:ring-golden-500"
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
