import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { getApi } from '@/api/apiClient';
import type { UserRole } from '@/api/types';
import { generateUUID } from '@/lib/uuid';
import { setAuthState, clearAuthState } from '@/api/authState';

/*
 * AuthContext
 *
 * Provides centralized authentication state management for the portal UI.
 * Responsibilities:
 * - Manage login/logout flows via the API adapter
 * - Store JWT, role, and tenant ID in sessionStorage for persistence
 * - Sync authorization state with `authState.ts` for API layer consumption
 * - Perform hydration and sanity checks on mount
 * - Expose role checks (isAdmin, isTenantAdmin) as derived booleans
 */

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
  // Authentication state initialized from sessionStorage (if user was previously logged in).
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!sessionStorage.getItem('portal_jwt'));
  // Role defaults to 'ADMIN' if not found (backward compat; ideally always present).
  const [role, setRole] = useState<UserRole>(() => {
    const stored = sessionStorage.getItem('portal_role');
    return (stored as UserRole) || 'ADMIN';
  });
  // Tenant ID is null for ADMIN role, but required for TENANT_ADMIN role.
  const [tenantId, setTenantId] = useState<string | null>(() => sessionStorage.getItem('portal_tenant_id'));
  // Optional message to display when session expires (401 from API).
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<string | null>(null);

  /*
   * Hydration & Sanity Checks
   *
   * On mount, we ensure that:
   * - A session ID always exists (used for tracing in API calls)
   * - Role + tenantId combinations are valid (e.g., TENANT_ADMIN must have tenantId)
   * - AuthState (used by apiClient for headers) is synced with React state
   * - Invalid combinations trigger forced logout
   */
  useEffect(() => {
    if (!sessionStorage.getItem('portal_session_id')) {
      sessionStorage.setItem('portal_session_id', generateUUID());
    }

    const jwt = sessionStorage.getItem('portal_jwt');
    if (!jwt) return;

    const storedRole = (sessionStorage.getItem('portal_role') as UserRole) || 'ADMIN';
    const storedTenant = sessionStorage.getItem('portal_tenant_id');

    // Validate role + tenant consistency: TENANT_ADMIN must have a tenantId.
    if (storedRole === 'TENANT_ADMIN' && !storedTenant) {
      // Invalid state — clear everything and force logout
      sessionStorage.removeItem('portal_jwt');
      sessionStorage.removeItem('portal_role');
      sessionStorage.removeItem('portal_tenant_id');
      clearAuthState();
      setIsAuthenticated(false);
      return;
    }

    // ADMIN role has no tenant context; TENANT_ADMIN uses its stored tenant.
    const effectiveTenant = storedRole === 'ADMIN' ? null : storedTenant;
    setRole(storedRole);
    setTenantId(effectiveTenant);
    // Sync the auth state so API headers and getEffectiveTenantId() use correct values.
    setAuthState(storedRole, effectiveTenant);
  }, []);

  /*
   * login
   *
   * Authenticate with backend using the provided credentials. On success:
   * - Store JWT and metadata in sessionStorage
   * - Sync role and tenant to context state and authState
   * - Update isAuthenticated to true
   *
   * On error, the API adapter throws and the caller (form) handles it.
   */
  const login = useCallback(async (username: string, password: string) => {
    const api = await getApi();
    const res = await api.login({ username, password });
    const loginRole: UserRole = res.data.role || 'ADMIN';
    // Compute effective tenant: ADMIN has none, TENANT_ADMIN uses the one from backend.
    const loginTenant = loginRole === 'ADMIN' ? null : (res.data.tenantId || null);

    // Persist auth data to sessionStorage for hydration on reload.
    sessionStorage.setItem('portal_jwt', res.data.access_token);
    sessionStorage.setItem('portal_role', loginRole);
    if (loginTenant) {
      sessionStorage.setItem('portal_tenant_id', loginTenant);
    } else {
      sessionStorage.removeItem('portal_tenant_id');
    }
    // Ensure session ID exists (created on first login if not set).
    if (!sessionStorage.getItem('portal_session_id')) {
      sessionStorage.setItem('portal_session_id', generateUUID());
    }

    // Sync to React state and authState so API layer sees the new role/tenant.
    setRole(loginRole);
    setTenantId(loginTenant);
    setAuthState(loginRole, loginTenant);
    setIsAuthenticated(true);
  }, []);

  /*
   * logout
   *
   * Clear all authentication state: JWT, role, tenant, and sync to authState.
   * This triggers React-Router guards to redirect to login on next navigation.
   */
  const logout = useCallback(() => {
    sessionStorage.removeItem('portal_jwt');
    sessionStorage.removeItem('portal_role');
    sessionStorage.removeItem('portal_tenant_id');
    clearAuthState();
    setIsAuthenticated(false);
    // Reset to default state (ADMIN, no tenant).
    setRole('ADMIN');
    setTenantId(null);
  }, []);

  const clearSessionMessage = useCallback(() => setSessionExpiredMessage(null), []);

  // Derived booleans for conditional rendering and route guards.
  const isAdmin = role === 'ADMIN';
  const isTenantAdmin = role === 'TENANT_ADMIN';

  return (
    <AuthContext.Provider value={{ isAuthenticated, role, tenantId, isAdmin, isTenantAdmin, login, logout, sessionExpiredMessage, clearSessionMessage }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * useAuth Hook
 *
 * Retrieve the current auth context. Must be called within an <AuthProvider>.
 * Provides access to authentication state and methods throughout the component tree.
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
