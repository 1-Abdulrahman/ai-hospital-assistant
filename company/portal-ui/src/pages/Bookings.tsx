import { useState } from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { DateRangeSelector, type DatePreset } from '@/components/shared/DateRangeSelector';
import { useAuth } from '@/contexts/AuthContext';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { Link } from 'react-router-dom';
import { format, subDays } from 'date-fns';
import { ChevronLeft, ChevronRight } from 'lucide-react';

// Bookings
//
// Admin/tenant browsable table of all appointment bookings. Supports filtering by
// date range, outcome status, specialty, and reason code with pagination. Correlation IDs
// link to request traces (admin only); tenant admins see truncated IDs for security.

export default function BookingsPage() {
  // Auth context for role-based UI rendering (tenant admin vs platform admin).
  const { isTenantAdmin } = useAuth();
  // Date range state: from (default -30 days) to today.
  const today = format(new Date(), 'yyyy-MM-dd');
  const [from, setFrom] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
  const [to, setTo] = useState(today);
  // Preset tracks selected date range button (e.g., '30d', '7d', 'custom').
  const [preset, setPreset] = useState<DatePreset>('30d');
  // Filter state: outcome status, specialty, and reason code for API query.
  const [status, setStatus] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [reasonCode, setReasonCode] = useState('');
  // Current page number (1-indexed) for pagination.
  const [page, setPage] = useState(1);

  const { data, loading, error, refetch } = useApiCall(
    (api) => api.getBookings({ from, to, status, specialty, reasonCode, page: String(page), pageSize: '20' }),
    [from, to, status, specialty, reasonCode, page]
  );

  // Calculate total pages from API response for pagination controls.
  const totalPages = data ? Math.ceil(data.total / data.pageSize) : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Bookings</h2>
      {/* Filter controls: date range, outcome status, specialty, and reason code. */}
      <div className="flex flex-wrap gap-3 items-end">
        {/* Date range selector with preset buttons (7d, 30d, custom). */}
        <DateRangeSelector from={from} to={to} preset={preset} onChange={(f, t, p) => { setFrom(f); setTo(t); setPreset(p); setPage(1); }} />
        {/* Outcome filter: SUCCESS, FAILED, or all. */}
        <Select value={status} onValueChange={(v) => { setStatus(v === 'all' ? '' : v); setPage(1); }}>
          <SelectTrigger className="w-[140px] h-9"><SelectValue placeholder="Outcome" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="SUCCESS">Success</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
          </SelectContent>
        </Select>
        {/* Specialty filter: free-text search for medical specialty. */}
        <Input placeholder="Specialty" value={specialty} onChange={(e) => { setSpecialty(e.target.value); setPage(1); }} className="w-[140px] h-9" />
        {/* Reason code filter: free-text search for cancellation/failure reason. */}
        <Input placeholder="Reason Code" value={reasonCode} onChange={(e) => { setReasonCode(e.target.value); setPage(1); }} className="w-[140px] h-9" />
      </div>

      {loading && <Skeleton className="h-64" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {data && data.items.length === 0 && <p className="text-muted-foreground text-sm">No bookings found.</p>}
      {/* Results table: displays bookings with all relevant metadata. */}
      {data && data.items.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>Booking ID</TableHead>
                <TableHead>Tenant</TableHead>
                <TableHead>Specialty</TableHead>
                <TableHead>Slot</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Correlation ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {/* Each booking row shows creation date, ID, tenant, specialty, slot time, and outcome. */}
              {data.items.map((b) => (
                <TableRow key={b.bookingId}>
                  <TableCell className="text-xs">{safeFormatDate(b.createdAt)}</TableCell>
                  <TableCell className="font-mono text-xs">{b.bookingId}</TableCell>
                  <TableCell className="text-xs">{b.tenantId || 'N/A'}</TableCell>
                  <TableCell>{b.specialty || 'N/A'}</TableCell>
                  <TableCell className="text-xs">{b.slotDate || 'N/A'} {b.slotTime || ''}</TableCell>
                  <TableCell><StatusBadge status={b.outcome} /></TableCell>
                  <TableCell className="text-xs">{b.reasonCode || 'N/A'}</TableCell>
                  {/* Correlation ID display: truncated + non-clickable for tenant admins (security), */}
                  {/* full ID + linked to traces page for platform admins. */}
                  <TableCell>
                {b.correlationId ? (
                  isTenantAdmin ? (
                    // Tenant admin: truncated ID (non-clickable) to limit trace data visibility.
                    <span className="text-xs font-mono">
                      {b.correlationId.slice(0, 8)}…
                    </span>
                  ) : (
                    // Platform admin: full clickable ID linked to request trace page.
                    <Link
                      to={`/traces?correlationId=${b.correlationId}`}
                      className="text-xs font-mono text-primary hover:underline"
                    >
                      {b.correlationId.slice(0, 8)}…
                    </Link>
                  )
                ) : (
                  'N/A'
                )}

                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {/* Pagination controls: total result count and prev/next buttons. */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{data.total} total results</p>
            <div className="flex items-center gap-2">
              {/* Previous page button: disabled on first page. */}
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
              <span className="text-sm">Page {page} of {totalPages}</span>
              {/* Next page button: disabled on last page. */}
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
