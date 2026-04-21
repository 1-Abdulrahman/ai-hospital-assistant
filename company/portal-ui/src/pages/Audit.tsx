import { useState } from 'react';
import { format, subDays } from 'date-fns';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import { DateRangeSelector, type DatePreset } from '@/components/shared/DateRangeSelector';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';

export default function AuditPage() {
  const today = format(new Date(), 'yyyy-MM-dd');
  const [from, setFrom] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
  const [to, setTo] = useState(today);
  const [preset, setPreset] = useState<DatePreset>('30d');
  const [eventType, setEventType] = useState('');
  const [outcome, setOutcome] = useState('');
  const [reasonCode, setReasonCode] = useState('');
  const [correlationId, setCorrelationId] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [page, setPage] = useState(1);

  const params: Record<string, string> = {
    from,
    to,
    page: String(page),
    pageSize: '20',
  };
  if (eventType) params.eventType = eventType;
  if (outcome) params.outcome = outcome;
  if (reasonCode) params.reasonCode = reasonCode;
  if (correlationId) params.correlationId = correlationId;
  if (sessionId) params.sessionId = sessionId;

  const { data, loading, error, refetch } = useApiCall(
    (api) => api.getAuditLogs(params),
    [from, to, eventType, outcome, reasonCode, correlationId, sessionId, page],
  );

  const totalPages = data ? Math.ceil(data.total / data.pageSize) : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Audit Logs</h2>

      <div className="flex flex-wrap gap-3 items-end">
        <DateRangeSelector
          from={from}
          to={to}
          preset={preset}
          onChange={(f, t, p) => {
            setFrom(f);
            setTo(t);
            setPreset(p);
            setPage(1);
          }}
        />
        <Input placeholder="Event type" value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(1); }} className="w-[170px] h-9" />
        <Input placeholder="Outcome" value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1); }} className="w-[140px] h-9" />
        <Input placeholder="Reason code" value={reasonCode} onChange={(e) => { setReasonCode(e.target.value); setPage(1); }} className="w-[170px] h-9" />
        <Input placeholder="Correlation ID" value={correlationId} onChange={(e) => { setCorrelationId(e.target.value); setPage(1); }} className="w-[220px] h-9" />
        <Input placeholder="Patient session ID" value={sessionId} onChange={(e) => { setSessionId(e.target.value); setPage(1); }} className="w-[220px] h-9" />
      </div>

      {loading && <Skeleton className="h-64" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground">No audit rows found.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timestamp</TableHead>
                <TableHead>Event Type</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Reason Code</TableHead>
                <TableHead>Correlation ID</TableHead>
                <TableHead>Summary</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((row, index) => (
                <TableRow key={`${row.timestamp}-${row.eventType}-${index}`}>
                  <TableCell className="text-xs">{safeFormatDate(row.timestamp)}</TableCell>
                  <TableCell className="text-xs font-medium">{row.eventType}</TableCell>
                  <TableCell><StatusBadge status={row.outcome} /></TableCell>
                  <TableCell className="text-xs">{row.reasonCode || 'N/A'}</TableCell>
                  <TableCell>
                    {row.correlationId ? (
                      <Link
                        to={`/traces?correlationId=${row.correlationId}`}
                        className="text-xs font-mono text-primary hover:underline"
                      >
                        {row.correlationId.slice(0, 8)}…
                      </Link>
                    ) : (
                      'N/A'
                    )}
                  </TableCell>
                  <TableCell className="text-sm">{row.safeSummary || row.message || 'N/A'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{data.total} total results</p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm">Page {page} of {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}