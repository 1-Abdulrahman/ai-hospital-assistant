import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { getApi } from '@/api/apiClient';
import type { UserRole } from '@/api/types';
import { generateUUID } from '@/lib/uuid';
import { setAuthState, clearAuthState } from '@/api/authState';

interface AuthContextType {
  isAuthenticated: boolean;
  role: UserRole;
  tenantId: string | null;
  isAdmin: boolean;
  isTenantAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  sessionExpiredMessage: string | null;
  clearSessionMessage: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!sessionStorage.getItem('portal_jwt'));
  const [role, setRole] = useState<UserRole>(() => {
    const stored = sessionStorage.getItem('portal_role');
    return (stored as UserRole) || 'ADMIN';
  });
  const [tenantId, setTenantId] = useState<string | null>(() => sessionStorage.getItem('portal_tenant_id'));
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  // Hydrate bridge + sanity checks on mount
  useEffect(() => {
    if (!sessionStorage.getItem('portal_session_id')) {
      sessionStorage.setItem('portal_session_id', generateUUID());
    }

    const jwt = sessionStorage.getItem('portal_jwt');
    if (!jwt) return;

    const storedRole = (sessionStorage.getItem('portal_role') as UserRole) || 'ADMIN';
    const storedTenant = sessionStorage.getItem('portal_tenant_id');

    // Sanity checks
    if (storedRole === 'TENANT_ADMIN' && !storedTenant) {
      // Invalid state — force logout
      sessionStorage.removeItem('portal_jwt');
      sessionStorage.removeItem('portal_role');
      sessionStorage.removeItem('portal_tenant_id');
      clearAuthState();
      setIsAuthenticated(false);
      return;
    }

    const effectiveTenant = storedRole === 'ADMIN' ? null : storedTenant;
    setRole(storedRole);
    setTenantId(effectiveTenant);
    setAuthState(storedRole, effectiveTenant);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const api = await getApi();
    const res = await api.login({ username, password });
    const loginRole: UserRole = res.data.role || 'ADMIN';
    const loginTenant = loginRole === 'ADMIN' ? null : (res.data.tenantId || null);

    sessionStorage.setItem('portal_jwt', res.data.access_token);
    sessionStorage.setItem('portal_role', loginRole);
    if (loginTenant) {
      sessionStorage.setItem('portal_tenant_id', loginTenant);
    } else {
      sessionStorage.removeItem('portal_tenant_id');
    }
    if (!sessionStorage.getItem('portal_session_id')) {
      sessionStorage.setItem('portal_session_id', generateUUID());
    }

    setRole(loginRole);
    setTenantId(loginTenant);
    setAuthState(loginRole, loginTenant);
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('portal_jwt');
    sessionStorage.removeItem('portal_role');
    sessionStorage.removeItem('portal_tenant_id');
    clearAuthState();
    setIsAuthenticated(false);
    setRole('ADMIN');
    setTenantId(null);
  }, []);

  const clearSessionMessage = useCallback(() => setSessionExpiredMessage(null), []);

  const isAdmin = role === 'ADMIN';
  const isTenantAdmin = role === 'TENANT_ADMIN';

  return (
    <AuthContext.Provider value={{ isAuthenticated, role, tenantId, isAdmin, isTenantAdmin, login, logout, sessionExpiredMessage, clearSessionMessage }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
