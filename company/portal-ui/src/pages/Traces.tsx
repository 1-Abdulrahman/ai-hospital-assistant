import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge } from '@/components/shared/StatusBadge';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { useApiCall } from '@/hooks/useApiCall';
import { safeFormatDate } from '@/lib/safeDate';
import { Search, Copy, Check } from 'lucide-react';
import type { TraceEvent } from '@/api/types';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  };
  return <Button variant="outline" size="sm" onClick={copy}>{copied ? <Check className="h-3 w-3 mr-1" /> : <Copy className="h-3 w-3 mr-1" />}{copied ? 'Copied' : 'Copy ID'}</Button>;
}

function Timeline({ events }: { events: TraceEvent[] }) {
  return (
    <div className="relative space-y-0">
      <div className="absolute left-[19px] top-2 bottom-2 w-0.5 bg-border" />
      {events.map((e, i) => (
        <div key={i} className="relative flex gap-4 pb-6">
          <div className="relative z-10 mt-1.5">
            <div className="w-3 h-3 rounded-full bg-primary border-2 border-background" />
          </div>
          <Card className="flex-1">
            <CardContent className="p-4 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground">{safeFormatDate(e.timestamp)}</span>
                <StatusBadge status={e.outcome} />
                <span className="text-xs font-medium">{e.eventType || 'N/A'}</span>
              </div>
              <p className="text-xs text-muted-foreground">Component: {e.component || 'N/A'}</p>
              {e.reasonCode && <p className="text-xs">Reason: {e.reasonCode}</p>}
              <p className="text-sm">{e.message || e.summary || e.safeSummary || 'N/A'}</p>
            </CardContent>
          </Card>
        </div>
      ))}
    </div>
  );
}

export default function TracesPage() {
  const [searchParams] = useSearchParams();
  const [correlationId, setCorrelationId] = useState(searchParams.get('correlationId') || '');
  const [sessionId, setSessionId] = useState('');
  const [searchType, setSearchType] = useState<'correlation' | 'session' | null>(
    searchParams.get('correlationId') ? 'correlation' : null
  );
  const [searchValue, setSearchValue] = useState(searchParams.get('correlationId') || '');

  const { data, loading, error, refetch } = useApiCall(
    (api) => {
      if (searchType === 'correlation' && searchValue) return api.getTracesByCorrelationId(searchValue);
      if (searchType === 'session' && searchValue) return api.getTracesBySessionId(searchValue);
      return Promise.resolve({ data: [] as TraceEvent[], requestCorrelationId: '' });
    },
    [searchType, searchValue]
  );

  const searchByCorrelation = () => { if (correlationId) { setSearchType('correlation'); setSearchValue(correlationId); } };
  const searchBySession = () => { if (sessionId) { setSearchType('session'); setSearchValue(sessionId); } };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Traces</h2>
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Correlation ID" value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} className="pl-9 w-[280px] h-9"
              onKeyDown={(e) => e.key === 'Enter' && searchByCorrelation()} />
          </div>
          <Button size="sm" onClick={searchByCorrelation}>Search</Button>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Patient Session ID" value={sessionId} onChange={(e) => setSessionId(e.target.value)} className="pl-9 w-[280px] h-9"
              onKeyDown={(e) => e.key === 'Enter' && searchBySession()} />
          </div>
          <Button size="sm" onClick={searchBySession}>Search</Button>
        </div>
      </div>

      {searchValue && <div className="flex items-center gap-2"><span className="text-sm text-muted-foreground">Showing trace for: <code className="font-mono">{searchValue.slice(0, 12)}…</code></span><CopyButton text={searchValue} /></div>}

      {loading && <Skeleton className="h-48" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {data && data.length === 0 && searchValue && <p className="text-muted-foreground text-sm">No trace events found.</p>}
      {!searchValue && <p className="text-muted-foreground text-sm">Enter a Correlation ID or Patient Session ID to view trace events.</p>}
      {data && data.length > 0 && <Timeline events={data} />}
    </div>
  );
}
