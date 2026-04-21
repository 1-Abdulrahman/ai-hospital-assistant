import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { cn } from '@/lib/utils';

export default function TenantsPage() {
  const [selectedTenantId, setSelectedTenantId] = useState('');

  const {
    data: tenants,
    loading: tenantsLoading,
    error: tenantsError,
    refetch: refetchTenants,
  } = useApiCall((api) => api.getTenants(), []);

  useEffect(() => {
    if (!selectedTenantId && tenants && tenants.length > 0) {
      setSelectedTenantId(tenants[0].tenantId);
    }
  }, [tenants, selectedTenantId]);

  const {
    data: tenantDetail,
    loading: detailLoading,
    error: detailError,
    refetch: refetchDetail,
  } = useApiCall(
    (api) =>
      selectedTenantId
        ? api.getTenantDetail(selectedTenantId)
        : Promise.resolve({ data: null as any, requestCorrelationId: '' }),
    [selectedTenantId],
  );

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Tenants</h2>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tenant catalog</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {tenantsLoading && <Skeleton className="h-48" />}
            {tenantsError && <ErrorBanner error={tenantsError} onRetry={refetchTenants} />}
            {tenants && tenants.length === 0 && (
              <p className="text-sm text-muted-foreground">No tenants found.</p>
            )}

            {tenants?.map((tenant) => (
              <button
                key={tenant.tenantId}
                type="button"
                onClick={() => setSelectedTenantId(tenant.tenantId)}
                className={cn(
                  'w-full rounded-md border p-3 text-left transition-colors',
                  selectedTenantId === tenant.tenantId
                    ? 'border-primary bg-primary/5'
                    : 'hover:bg-muted/40'
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium">{tenant.name}</div>
                    <div className="text-xs text-muted-foreground">{tenant.tenantId}</div>
                  </div>
                  <StatusBadge status={tenant.status} />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  Created: {safeFormatDate(tenant.createdAt) || 'N/A'}
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tenant detail</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {detailLoading && <Skeleton className="h-64" />}
            {detailError && <ErrorBanner error={detailError} onRetry={refetchDetail} />}

            {tenantDetail && (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="text-xs text-muted-foreground">Tenant ID</div>
                    <div className="text-sm font-medium">{tenantDetail.tenantId}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Name</div>
                    <div className="text-sm font-medium">{tenantDetail.name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Status</div>
                    <StatusBadge status={tenantDetail.status} />
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Created</div>
                    <div className="text-sm">{safeFormatDate(tenantDetail.createdAt) || 'N/A'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">FHIR Status</div>
                    <StatusBadge status={tenantDetail.fhirStatus || 'UNKNOWN'} />
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">SMTP Status</div>
                    <StatusBadge status={tenantDetail.smtpStatus || 'UNKNOWN'} />
                  </div>
                </div>

                <div>
                  <div className="text-sm font-medium mb-2">Allowed origins</div>
                  <div className="space-y-2">
                    {tenantDetail.allowedOrigins?.map((origin) => (
                      <div key={origin} className="rounded-md border p-2 text-xs font-mono">
                        {origin}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="text-sm font-medium mb-2">Feature flags</div>
                  <div className="grid gap-2 md:grid-cols-2">
                    {Object.entries(tenantDetail.featureFlags || {}).map(([key, value]) => (
                      <div key={key} className="rounded-md border p-3">
                        <div className="text-xs text-muted-foreground">{key}</div>
                        <div className="mt-1">
                          <StatusBadge status={value ? 'ACTIVE' : 'DOWN'} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {!detailLoading && !tenantDetail && (
              <p className="text-sm text-muted-foreground">Select a tenant to view details.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}