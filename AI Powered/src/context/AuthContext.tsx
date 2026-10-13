import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, UserRole } from '../types';
import { apiService } from '../services/api.service';

interface AuthContextType {
  user: User | null;
  role: UserRole;
  isAuthenticated: boolean;
  isLoading: boolean;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  switchUser?: (userId: string) => void;
  switchRole?: (role: UserRole) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

import { loadChatData, saveChatData } from '../services/chatStorage';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => apiService.getToken());
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => Boolean(apiService.getToken()));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const logout = () => {
    apiService.logout();
    setToken(null);
    setUser(null);
    setIsAuthenticated(false);
  };

  useEffect(() => {
    // Register 401 handler for automatic logout
    apiService.setOnUnauthorized(() => {
      logout();
    });

    // Check existing session
    const initAuth = async (retries = 3) => {
      const existingToken = apiService.getToken();
      if (existingToken) {
        try {
          const me = await apiService.getMe();
          if (me) {
            setUser(me);
            setIsAuthenticated(true);
            setToken(existingToken);
          } else {
            logout();
          }
        } catch (error) {
          if (retries > 0) {
            setTimeout(() => initAuth(retries - 1), 1000);
            return; // Wait for retry to finish
          }
          logout();
        }
      } else {
        setIsAuthenticated(false);
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = async (username: string, password: string) => {
    const res = await apiService.login(username, password);
    setToken(res.accessToken);
    setUser(res.user);
    setIsAuthenticated(true);
  };

  const role: UserRole = user?.role === 'admin' ? 'admin' : 'user';

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        isAuthenticated,
        isLoading,
        token,
        login,
        logout,
        switchUser: () => {},
        switchRole: () => {},
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
