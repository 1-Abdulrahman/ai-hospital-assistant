import type { UserRole } from './types';

// authState
//
// Module-level cache for current user role and tenant ID. Provides lazy hydration
// from sessionStorage and derives the effective tenant ID for API calls based on role.
// Used by AuthContext and API adapters to avoid redundant sessionStorage access.

// Current user role cached in memory (e.g., 'ADMIN', 'TENANT_ADMIN').
let currentRole: UserRole | null = null;
// Current tenant ID (required for TENANT_ADMIN, null/unused for ADMIN).
let currentTenantId: string | null = null;

// Store the current user role and tenant ID in memory.
// Called by AuthContext.login() after JWT validation and sessionStorage persistence.
export function setAuthState(role: UserRole | null, tenantId: string | null) {
  currentRole = role;
  currentTenantId = tenantId;
}

// Lazy-load auth state from sessionStorage on first access if not already set in memory.
// Allows API calls to work before AuthContext hydration completes on page load.
function hydrateFromSessionStorageIfEmpty() {
  if (currentRole !== null) return;
  const storedRole = sessionStorage.getItem('portal_role');
  const storedTenant = sessionStorage.getItem('portal_tenant_id');
  // Populate memory cache from sessionStorage for subsequent calls.
  if (storedRole) currentRole = storedRole as UserRole;
  if (storedTenant) currentTenantId = storedTenant;
}

// Return the tenant ID for API calls based on current role.
// TENANT_ADMIN: returns their assigned tenant ID (or 'demo' fallback if not set).
// ADMIN: always returns 'demo' (admin queries are not tenant-scoped).
export function getEffectiveTenantId(): string {
  hydrateFromSessionStorageIfEmpty();
  // TENANT_ADMIN uses their scoped tenant; fallback to 'demo' if missing.
  if (currentRole === 'TENANT_ADMIN') return currentTenantId || 'demo';
  // ADMIN (and any unrecognized role) uses 'demo' tenant.
  return 'demo';
}

// Clear all cached auth state (called on logout).
export function clearAuthState() {
  currentRole = null;
  currentTenantId = null;
}
