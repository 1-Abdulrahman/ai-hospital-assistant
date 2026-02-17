import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getApi } from '@/api/apiClient';
import type { ApiError } from '@/api/types';
import { generateUUID } from '@/lib/uuid';

interface AuthContextType {
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  sessionExpiredMessage: string | null;
  clearSessionMessage: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!sessionStorage.getItem('portal_jwt'));
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  useEffect(() => {
    // Ensure portalSessionId exists
    if (!sessionStorage.getItem('portal_session_id')) {
      sessionStorage.setItem('portal_session_id', generateUUID());
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const api = await getApi();
    const res = await api.login({ username, password });
    sessionStorage.setItem('portal_jwt', res.data.access_token);
    if (!sessionStorage.getItem('portal_session_id')) {
      sessionStorage.setItem('portal_session_id', generateUUID());
    }
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('portal_jwt');
    setIsAuthenticated(false);
  }, []);

  const clearSessionMessage = useCallback(() => setSessionExpiredMessage(null), []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout, sessionExpiredMessage, clearSessionMessage }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
