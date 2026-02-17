import { useState } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { DateRangeSelector, type DatePreset } from '@/components/shared/DateRangeSelector';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { Link } from 'react-router-dom';
import { format, subDays } from 'date-fns';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';

export default function AuditPage() {
  const today = format(new Date(), 'yyyy-MM-dd');
  const [from, setFrom] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
  const [to, setTo] = useState(today);
  const [preset, setPreset] = useState<DatePreset>('30d');
  const [correlationId, setCorrelationId] = useState('');
  const [eventType, setEventType] = useState('');
  const [outcome, setOutcome] = useState('');
  const [reasonCode, setReasonCode] = useState('');
  const [page, setPage] = useState(1);

  const params: Record<string, string> = { from, to, page: String(page), pageSize: '20' };
  if (correlationId) params.correlationId = correlationId;
  if (eventType) params.eventType = eventType;
  if (outcome) params.outcome = outcome;
  if (reasonCode) params.reasonCode = reasonCode;

  const { data, loading, error, refetch } = useApiCall((api) => api.getAuditLogs(params), [from, to, correlationId, eventType, outcome, reasonCode, page]);
  const totalPages = data ? Math.ceil(data.total / data.pageSize) : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Audit Logs</h2>
      <div className="flex flex-wrap gap-3 items-end">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search by Correlation ID" value={correlationId} onChange={(e) => { setCorrelationId(e.target.value); setPage(1); }} className="pl-9 w-[260px] h-9" />
        </div>
        <DateRangeSelector from={from} to={to} preset={preset} onChange={(f, t, p) => { setFrom(f); setTo(t); setPreset(p); setPage(1); }} />
        <Input placeholder="Event Type" value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(1); }} className="w-[140px] h-9" />
        <Select value={outcome} onValueChange={(v) => { setOutcome(v === 'all' ? '' : v); setPage(1); }}>
          <SelectTrigger className="w-[120px] h-9"><SelectValue placeholder="Outcome" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All</SelectItem><SelectItem value="SUCCESS">Success</SelectItem><SelectItem value="FAILED">Failed</SelectItem></SelectContent>
        </Select>
        <Input placeholder="Reason Code" value={reasonCode} onChange={(e) => { setReasonCode(e.target.value); setPage(1); }} className="w-[140px] h-9" />
      </div>

      {loading && <Skeleton className="h-64" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {data && data.items.length === 0 && <p className="text-muted-foreground text-sm">No audit logs found.</p>}
      {data && data.items.length > 0 && (
        <>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Timestamp</TableHead><TableHead>Event Type</TableHead><TableHead>Outcome</TableHead>
              <TableHead>Reason Code</TableHead><TableHead>Idempotency Key</TableHead><TableHead>Correlation ID</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {data.items.map((a, i) => (
                <TableRow key={i}>
                  <TableCell className="text-xs">{safeFormatDate(a.timestamp)}</TableCell>
                  <TableCell className="text-xs">{a.eventType || 'N/A'}</TableCell>
                  <TableCell><StatusBadge status={a.outcome} /></TableCell>
                  <TableCell className="text-xs">{a.reasonCode || 'N/A'}</TableCell>
                  <TableCell className="font-mono text-xs">{a.idempotencyKey ? '••••••' : 'N/A'}</TableCell>
                  <TableCell>
                    {a.correlationId ? (
                      <Link to={`/traces?correlationId=${a.correlationId}`} className="text-xs font-mono text-primary hover:underline">{a.correlationId.slice(0, 8)}…</Link>
                    ) : 'N/A'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{data.total} total results</p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
              <span className="text-sm">Page {page} of {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
