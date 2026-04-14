import { ComingSoonPanel } from '@/components/shared/ComingSoonPanel';

export default function AuditPage() {
  return (
    <ComingSoonPanel
      title="Audit Logs"
      description="Detailed audit filtering is deferred for this checkpoint. Real traceability is already available today through the Sessions and Traces pages backed by live event data."
      bullets={[
        'Advanced audit search and pagination',
        'Correlation and reason-code filtering',
        'Broader operational drill-down views',
      ]}
    />
  );
}