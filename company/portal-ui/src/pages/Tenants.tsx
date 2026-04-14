import { ComingSoonPanel } from '@/components/shared/ComingSoonPanel';

export default function TenantsPage() {
  return (
    <ComingSoonPanel
      title="Tenants"
      description="Tenant administration is intentionally deferred for this checkpoint. The portal currently focuses on real operational traceability, session visibility, and dashboard analytics."
      bullets={[
        'Tenant catalog and detailed feature flag views',
        'Integration visibility per tenant',
        'Richer platform administration controls',
      ]}
    />
  );
}