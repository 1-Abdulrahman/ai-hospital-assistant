import type { UserRole } from './types';

let currentRole: UserRole | null = null;
let currentTenantId: string | null = null;

export function setAuthState(role: UserRole | null, tenantId: string | null) {
  currentRole = role;
  currentTenantId = tenantId;
}

function hydrateFromSessionStorageIfEmpty() {
  if (currentRole !== null) return;
  const storedRole = sessionStorage.getItem('portal_role');
  const storedTenant = sessionStorage.getItem('portal_tenant_id');
  if (storedRole) currentRole = storedRole as UserRole;
  if (storedTenant) currentTenantId = storedTenant;
}

export function getEffectiveTenantId(): string {
  hydrateFromSessionStorageIfEmpty();
  if (currentRole === 'TENANT_ADMIN') return currentTenantId || 'demo';
  return 'demo';
}

export function clearAuthState() {
  currentRole = null;
  currentTenantId = null;
}
