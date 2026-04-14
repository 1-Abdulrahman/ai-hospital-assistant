import { ComingSoonPanel } from '@/components/shared/ComingSoonPanel';

export default function NlpMonitoringPage() {
  return (
    <ComingSoonPanel
      title="NLP Monitoring"
      description="NLP monitoring is deferred for this checkpoint. The current focus is on real booking traceability, session timelines, and portal-backed operational visibility."
      bullets={[
        'Model health and threshold monitoring',
        'Recent classification views',
        'Confidence and ambiguity trend analysis',
      ]}
    />
  );
}