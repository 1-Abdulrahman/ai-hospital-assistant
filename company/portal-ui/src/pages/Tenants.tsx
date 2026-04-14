import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ModeAwareComingSoon } from '@/components/shared/ModeAwareComingSoon';

function TenantsPreview() {
  const tenants = [
    { tenantId: 'demo', name: 'Demo Tenant', status: 'ACTIVE' },
    { tenantId: 'platform', name: 'Platform Administration', status: 'ACTIVE' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-2xl font-bold">Tenants</h2>
        <Badge variant="outline" className="bg-blue-500/15 text-blue-700 border-blue-300">
          Mock preview
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Future tenant administration preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {tenants.map((tenant) => (
            <div key={tenant.tenantId} className="rounded-md border p-3 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{tenant.name}</div>
                <div className="text-xs text-muted-foreground">{tenant.tenantId}</div>
              </div>
              <Badge variant="outline">{tenant.status}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export default function TenantsPage() {
  return (
    <ModeAwareComingSoon
      title="Tenants"
      description="Tenant administration is intentionally deferred for this checkpoint. The portal currently focuses on real operational traceability, session visibility, and dashboard analytics."
      bullets={[
        'Tenant catalog and detailed feature flag views',
        'Integration visibility per tenant',
        'Richer platform administration controls',
      ]}
      preview={<TenantsPreview />}
    />
  );
}