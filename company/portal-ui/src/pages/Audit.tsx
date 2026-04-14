import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ModeAwareComingSoon } from '@/components/shared/ModeAwareComingSoon';

function AuditPreview() {
  const rows = [
    {
      timestamp: '2026-04-15T09:15:00Z',
      eventType: 'BOOKING_CONFIRMED',
      outcome: 'SUCCESS',
      reasonCode: 'OK',
      safeSummary: 'Appointment booked successfully for Cardiology.',
    },
    {
      timestamp: '2026-04-15T09:12:00Z',
      eventType: 'AVAILABILITY_REQUESTED',
      outcome: 'SUCCESS',
      reasonCode: 'OK',
      safeSummary: 'Availability retrieved for Cardiology.',
    },
    {
      timestamp: '2026-04-15T09:10:00Z',
      eventType: 'SESSION_STARTED',
      outcome: 'SUCCESS',
      reasonCode: 'OK',
      safeSummary: 'User started scheduling flow.',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-2xl font-bold">Audit Logs</h2>
        <Badge variant="outline" className="bg-blue-500/15 text-blue-700 border-blue-300">
          Mock preview
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Future audit experience preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {rows.map((row, index) => (
            <div key={index} className="rounded-md border p-3 space-y-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-muted-foreground">{row.timestamp}</span>
                <Badge variant="outline">{row.outcome}</Badge>
              </div>
              <div className="text-sm font-medium">{row.eventType}</div>
              <div className="text-xs text-muted-foreground">
                Reason: {row.reasonCode}
              </div>
              <div className="text-sm">{row.safeSummary}</div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AuditPage() {
  return (
    <ModeAwareComingSoon
      title="Audit Logs"
      description="Detailed audit filtering is deferred for this checkpoint. Real traceability is already available today through the Sessions and Traces pages backed by live event data."
      bullets={[
        'Advanced audit search and pagination',
        'Correlation and reason-code filtering',
        'Broader operational drill-down views',
      ]}
      preview={<AuditPreview />}
    />
  );
}