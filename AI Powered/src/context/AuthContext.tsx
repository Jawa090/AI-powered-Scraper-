import React, { createContext, useContext } from 'react';
import { useDataOps } from './DataOpsContext';
import { User, UserRole } from '../types';

interface AuthContextType {
  user: User;
  role: UserRole;
  isAuthenticated: boolean;
  login: (email: string) => void;
  logout: () => void;
  switchUser: (userId: string) => void;
  switchRole: (role: UserRole) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { currentUser, switchUser, switchRole } = useDataOps();

  const login = (email: string) => {
    // In mock mode, login always succeeds
  };

  const logout = () => {
    // Return to login
  };

  return (
    <AuthContext.Provider
      value={{
        user: currentUser,
        role: currentUser.role,
        isAuthenticated: true,
        login,
        logout,
        switchUser,
        switchRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};
