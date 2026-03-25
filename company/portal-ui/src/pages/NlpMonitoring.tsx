import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';

export default function NlpMonitoringPage() {
  const { data: stats, loading: statsLoading, error: statsError, refetch: refetchStats } = useApiCall((api) => api.getNlpStats(), []);
  const { data: recent, loading: recentLoading, error: recentError, refetch: refetchRecent } = useApiCall((api) => api.getNlpRecent(20), []);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">NLP Monitoring</h2>

      {/* Stats Panel */}
      {statsLoading && <Skeleton className="h-32" />}
      {statsError && <ErrorBanner error={statsError} onRetry={refetchStats} />}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card><CardContent className="pt-4"><p className="text-2xl font-bold">{stats.loadedLabels}</p><p className="text-xs text-muted-foreground">Loaded Labels</p></CardContent></Card>
          <Card><CardContent className="pt-4">
            <div className="space-y-1">{Object.entries(stats.thresholds).map(([k, v]) => <p key={k} className="text-xs">{k}: {v}</p>)}</div>
            <p className="text-xs text-muted-foreground mt-1">Thresholds</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4"><p className="text-lg font-semibold">{stats.modelName || 'N/A'}</p><p className="text-xs text-muted-foreground">{stats.modelVersion || 'N/A'}</p><p className="text-xs text-muted-foreground">Model</p></CardContent></Card>
          <Card><CardContent className="pt-4"><p className="text-sm">{safeFormatDate(stats.lastModelLoadTime)}</p><p className="text-xs text-muted-foreground">Last Model Load</p></CardContent></Card>
        </div>
      )}

      {/* Recent Classifications */}
      <h3 className="text-lg font-semibold">Recent Classifications</h3>
      {recentLoading && <Skeleton className="h-48" />}
      {recentError && <ErrorBanner error={recentError} onRetry={refetchRecent} />}
      {recent && recent.length === 0 && <p className="text-muted-foreground text-sm">No recent classifications.</p>}
      {recent && recent.length > 0 && (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Timestamp</TableHead><TableHead>Input Summary</TableHead><TableHead>Predicted Label</TableHead>
            <TableHead>Confidence</TableHead><TableHead>Ambiguity</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {recent.map((c, i) => (
              <TableRow key={i}>
                <TableCell className="text-xs">{safeFormatDate(c.timestamp)}</TableCell>
                <TableCell className="text-sm max-w-[300px] truncate">{c.inputSummary || 'Redacted'}</TableCell>
                <TableCell><Badge variant="secondary">{c.predictedLabel}</Badge></TableCell>
                <TableCell className="text-xs font-mono">{(c.confidence * 100).toFixed(1)}%</TableCell>
                <TableCell>{c.ambiguity ? <Badge variant="outline" className="bg-amber-500/15 text-amber-700 border-amber-300 text-xs">Ambiguous</Badge> : <span className="text-xs text-muted-foreground">—</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
