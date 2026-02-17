import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { DateRangeSelector, type DatePreset } from '@/components/shared/DateRangeSelector';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { format, subDays } from 'date-fns';

function HealthCard({ title, fetchFn }: { title: string; fetchFn: string }) {
  const { data, loading, error, refetch } = useApiCall(
    (api) => fetchFn === 'health' ? api.getHealth() : api.getFhirStatus(),
    [fetchFn]
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Button variant="ghost" size="icon" onClick={refetch} className="h-8 w-8">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent>
        {loading && <Skeleton className="h-8 w-20" />}
        {error && <ErrorBanner error={error} onRetry={refetch} />}
        {data && (
          <div className="space-y-1">
            <StatusBadge status={data.status} />
            <p className="text-xs text-muted-foreground">Last checked: {safeFormatDate(data.timestamp)}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const today = format(new Date(), 'yyyy-MM-dd');
  const [from, setFrom] = useState(format(subDays(new Date(), 7), 'yyyy-MM-dd'));
  const [to, setTo] = useState(today);
  const [preset, setPreset] = useState<DatePreset>('7d');

  const { data: analytics, loading: analyticsLoading, error: analyticsError, refetch: refetchAnalytics } = useApiCall(
    (api) => api.getAnalyticsSummary(from, to), [from, to]
  );

  const { data: recent, loading: recentLoading, error: recentError, refetch: refetchRecent } = useApiCall(
    (api) => api.getRecentBookings(10), []
  );

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>

      {/* Health widgets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <HealthCard title="Backend Health" fetchFn="health" />
        <HealthCard title="FHIR Integration" fetchFn="fhir" />
      </div>

      {/* Analytics */}
      <div className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-lg font-semibold">Summary Analytics</h3>
          <DateRangeSelector from={from} to={to} preset={preset} onChange={(f, t, p) => { setFrom(f); setTo(t); setPreset(p); }} />
        </div>
        {analyticsLoading && <div className="grid grid-cols-2 md:grid-cols-5 gap-4">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>}
        {analyticsError && <ErrorBanner error={analyticsError} onRetry={refetchAnalytics} />}
        {analytics && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card><CardContent className="pt-4"><p className="text-2xl font-bold">{analytics.totalBookings}</p><p className="text-xs text-muted-foreground">Total Bookings</p></CardContent></Card>
            <Card><CardContent className="pt-4"><p className="text-2xl font-bold text-destructive">{analytics.bookingFailures}</p><p className="text-xs text-muted-foreground">Failures</p></CardContent></Card>
            <Card><CardContent className="pt-4"><p className="text-2xl font-bold">{analytics.droppedSessions}</p><p className="text-xs text-muted-foreground">Dropped Sessions</p></CardContent></Card>
            <Card><CardContent className="pt-4"><div className="space-y-1">{analytics.topReasonCodes.map((r) => <p key={r.code} className="text-xs">{r.code}: {r.count}</p>)}</div><p className="text-xs text-muted-foreground mt-1">Top Reason Codes</p></CardContent></Card>
            <Card><CardContent className="pt-4"><div className="space-y-1">{(analytics.topSpecialties as any[]).map((s: any) => <p key={s.code || s.specialty} className="text-xs">{s.code || s.specialty}: {s.count}</p>)}</div><p className="text-xs text-muted-foreground mt-1">Top Specialties</p></CardContent></Card>
          </div>
        )}
      </div>

      {/* Recent Activity */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Recent Activity</h3>
        {recentLoading && <Skeleton className="h-48" />}
        {recentError && <ErrorBanner error={recentError} onRetry={refetchRecent} />}
        {recent && recent.length === 0 && <p className="text-muted-foreground text-sm">No recent activity.</p>}
        {recent && recent.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>Booking ID</TableHead>
                <TableHead>Specialty</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Correlation ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.map((b) => (
                <TableRow key={b.bookingId}>
                  <TableCell className="text-xs">{safeFormatDate(b.createdAt)}</TableCell>
                  <TableCell className="font-mono text-xs">{b.bookingId}</TableCell>
                  <TableCell>{b.specialty || 'N/A'}</TableCell>
                  <TableCell><StatusBadge status={b.outcome} /></TableCell>
                  <TableCell>
                    {b.correlationId ? (
                      <Link to={`/traces?correlationId=${b.correlationId}`} className="text-xs font-mono text-primary hover:underline">
                        {b.correlationId.slice(0, 8)}…
                      </Link>
                    ) : 'N/A'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
