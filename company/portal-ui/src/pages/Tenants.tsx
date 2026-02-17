import { useState } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { ArrowLeft } from 'lucide-react';
import type { TenantDetail } from '@/api/types';

export default function TenantsPage() {
  const [selectedTenant, setSelectedTenant] = useState<string | null>(null);

  const { data: tenants, loading, error, refetch } = useApiCall((api) => api.getTenants(), []);
  const { data: detail, loading: detailLoading, error: detailError } = useApiCall<TenantDetail | null>(
    (api) => selectedTenant ? api.getTenantDetail(selectedTenant) : Promise.resolve({ data: null as any, requestCorrelationId: '' }),
    [selectedTenant]
  );

  if (selectedTenant && detail) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setSelectedTenant(null)}><ArrowLeft className="h-4 w-4 mr-1" /> Back</Button>
          <h2 className="text-2xl font-bold">Tenant: {detail.tenantId}</h2>
        </div>
        {detailLoading && <Skeleton className="h-48" />}
        {detailError && <ErrorBanner error={detailError} />}
        {detail && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card><CardHeader><CardTitle className="text-sm">General</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
              <p><span className="text-muted-foreground">ID:</span> {detail.tenantId}</p>
              <p><span className="text-muted-foreground">Name:</span> {detail.name}</p>
              <p><span className="text-muted-foreground">Status:</span> <StatusBadge status={detail.status} /></p>
              <p><span className="text-muted-foreground">Created:</span> {safeFormatDate(detail.createdAt)}</p>
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="text-sm">Allowed Origins</CardTitle></CardHeader><CardContent>
              {detail.allowedOrigins?.length ? detail.allowedOrigins.map((o) => <Badge key={o} variant="secondary" className="mr-1 mb-1">{o}</Badge>) : <span className="text-sm text-muted-foreground">N/A</span>}
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="text-sm">Feature Flags</CardTitle></CardHeader><CardContent>
              {detail.featureFlags ? Object.entries(detail.featureFlags).map(([k, v]) => (
                <p key={k} className="text-sm"><span className="text-muted-foreground">{k}:</span> {v ? '✅' : '❌'}</p>
              )) : <span className="text-sm text-muted-foreground">N/A</span>}
            </CardContent></Card>
            <Card><CardHeader><CardTitle className="text-sm">Integrations</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
              <p><span className="text-muted-foreground">FHIR:</span> {detail.fhirStatus ? <StatusBadge status={detail.fhirStatus} /> : 'N/A'}</p>
              <p><span className="text-muted-foreground">SMTP:</span> {detail.smtpStatus || 'SMTP status not exposed in MVP'}</p>
            </CardContent></Card>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Tenants</h2>
      {loading && <Skeleton className="h-32" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {tenants && tenants.length === 0 && <p className="text-muted-foreground text-sm">No tenants found.</p>}
      {tenants && tenants.length > 0 && (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Tenant ID</TableHead><TableHead>Name</TableHead><TableHead>Status</TableHead><TableHead>Created</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {tenants.map((t) => (
              <TableRow key={t.tenantId} className="cursor-pointer" onClick={() => setSelectedTenant(t.tenantId)}>
                <TableCell className="font-mono text-xs">{t.tenantId}</TableCell>
                <TableCell>{t.name}</TableCell>
                <TableCell><StatusBadge status={t.status} /></TableCell>
                <TableCell className="text-xs">{safeFormatDate(t.createdAt)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
