import { useState } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { DateRangeSelector, type DatePreset } from '@/components/shared/DateRangeSelector';
import { useAuth } from '@/contexts/AuthContext';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { Link } from 'react-router-dom';
import { format, subDays } from 'date-fns';
import { ChevronLeft, ChevronRight } from 'lucide-react';

// Sessions
//
// Admin page for monitoring patient chat sessions. Shows all active, completed, dropped,
// and failed sessions with filtering by date range and status. Tenant admins see their
// scoped sessions only; platform admins can filter by tenant. Links to detailed traces
// and request history for each session.

export default function SessionsPage() {
  const { isTenantAdmin } = useAuth();
  const today = format(new Date(), 'yyyy-MM-dd');
  const [from, setFrom] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
  const [to, setTo] = useState(today);
  const [preset, setPreset] = useState<DatePreset>('30d');
  const [status, setStatus] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [page, setPage] = useState(1);

  const params: Record<string, string> = { from, to, page: String(page), pageSize: '20' };
  if (status) params.status = status;
  if (tenantId) params.tenantId = tenantId;

  const { data, loading, error, refetch } = useApiCall(
    (api) => api.getSessions(params),
    [from, to, status, tenantId, page],
  );

  const totalPages = data ? Math.ceil(data.total / data.pageSize) : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Sessions</h2>

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

        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v === 'all' ? '' : v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[140px] h-9">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="ACTIVE">Active</SelectItem>
            <SelectItem value="COMPLETED">Completed</SelectItem>
            <SelectItem value="DROPPED">Dropped</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
          </SelectContent>
        </Select>

        {!isTenantAdmin && (
          <Input
            placeholder="Tenant ID"
            value={tenantId}
            onChange={(e) => {
              setTenantId(e.target.value);
              setPage(1);
            }}
            className="w-[140px] h-9"
          />
        )}
      </div>

      {loading && <Skeleton className="h-64" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {data && data.items.length === 0 && (
        <p className="text-muted-foreground text-sm">No sessions found.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patient Session ID</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Last Event</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Reason Code</TableHead>
                <TableHead>Correlation ID</TableHead>
                {!isTenantAdmin && <TableHead></TableHead>}
              </TableRow>
            </TableHeader>

            <TableBody>
              {data.items.map((s) => (
                <TableRow key={s.sessionId}>
                  <TableCell className="font-mono text-xs">
                    {s.sessionId.slice(0, 8)}…
                  </TableCell>
                  <TableCell className="text-xs">{safeFormatDate(s.startedAt)}</TableCell>
                  <TableCell className="text-xs">{safeFormatDate(s.lastEventAt)}</TableCell>
                  <TableCell>
                    <StatusBadge status={s.status} />
                  </TableCell>
                  <TableCell className="text-xs">{s.finalReasonCode || 'N/A'}</TableCell>
                  <TableCell>
                    {s.correlationId ? (
                      isTenantAdmin ? (
                        <span className="text-xs font-mono">
                          {s.correlationId.slice(0, 8)}…
                        </span>
                      ) : (
                        <Link
                          to={`/traces?correlationId=${s.correlationId}`}
                          className="text-xs font-mono text-primary hover:underline"
                        >
                          {s.correlationId.slice(0, 8)}…
                        </Link>
                      )
                    ) : (
                      'N/A'
                    )}
                  </TableCell>

                  {!isTenantAdmin && (
                    <TableCell>
                      <Link to={`/traces?sessionId=${s.sessionId}`}>
                        <Button variant="outline" size="sm">
                          Open Trace
                        </Button>
                      </Link>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {data.total} total results
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>

              <span className="text-sm">
                Page {page} of {totalPages}
              </span>

              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}