import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

export default function NlpMonitoringPage() {
  const {
    data: stats,
    loading: statsLoading,
    error: statsError,
    refetch: refetchStats,
  } = useApiCall((api) => api.getNlpStats(), []);

  const {
    data: recent,
    loading: recentLoading,
    error: recentError,
    refetch: refetchRecent,
  } = useApiCall((api) => api.getNlpRecent(20), []);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">NLP Monitoring</h2>

      <div className="grid gap-4 md:grid-cols-4">
        {statsLoading && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        {statsError && <ErrorBanner error={statsError} onRetry={refetchStats} />}
        {stats && (
          <>
            <Card>
              <CardContent className="pt-4">
                <p className="text-2xl font-bold">{stats.loadedLabels}</p>
                <p className="text-xs text-muted-foreground">Loaded Labels</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm font-medium">{stats.modelName || 'N/A'}</p>
                <p className="text-xs text-muted-foreground">Model Name</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <p className="text-sm font-medium">{stats.modelVersion || 'N/A'}</p>
                <p className="text-xs text-muted-foreground">Model Version</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <div className="space-y-1 text-xs">
                  {Object.entries(stats.thresholds || {}).map(([key, value]) => (
                    <div key={key}>
                      {key}: {value}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-1">Thresholds</p>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent NLP classifications</CardTitle>
        </CardHeader>
        <CardContent>
          {recentLoading && <Skeleton className="h-64" />}
          {recentError && <ErrorBanner error={recentError} onRetry={refetchRecent} />}
          {recent && recent.length === 0 && (
            <p className="text-sm text-muted-foreground">No recent NLP classifications found.</p>
          )}

          {recent && recent.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Input Summary</TableHead>
                  <TableHead>Predicted Label</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Ambiguous</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((row, index) => (
                  <TableRow key={`${row.timestamp}-${row.predictedLabel}-${index}`}>
                    <TableCell className="text-xs">{safeFormatDate(row.timestamp)}</TableCell>
                    <TableCell className="text-sm">{row.inputSummary || 'N/A'}</TableCell>
                    <TableCell className="text-sm font-medium">{row.predictedLabel}</TableCell>
                    <TableCell className="text-sm">{Math.round(row.confidence * 100)}%</TableCell>
                    <TableCell>
                      <StatusBadge status={row.ambiguity ? 'DEGRADED' : 'SUCCESS'} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {stats?.lastModelLoadTime && (
            <div className="mt-4 text-xs text-muted-foreground">
              Last model load: {safeFormatDate(stats.lastModelLoadTime)}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}