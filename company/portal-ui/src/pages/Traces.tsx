import { useState } from 'react';
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

// CopyButton
//
// Reusable button component that copies text to clipboard and shows
// visual feedback (changes to "Copied" with checkmark) for 2 seconds.

function CopyButton({ text }: { text: string }) {
  // Track copy state for UI feedback (show "Copied" for 2 seconds).
  const [copied, setCopied] = useState(false);

  // Copy text to clipboard and show confirmation.
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      // Reset "Copied" message after 2 seconds.
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Button variant="outline" size="sm" onClick={copy}>
      {copied ? <Check className="h-3 w-3 mr-1" /> : <Copy className="h-3 w-3 mr-1" />}
      {copied ? 'Copied' : 'Copy ID'}
    </Button>
  );
}

// Format trace event details for display based on the label type.
// Special formatting: clarification details as bullet list, preprocessing actions as tags,
// top candidates as numbered list. Default: plain text with whitespace preserved.
function formatTraceValue(label: string, value: string): React.ReactNode {
  // Clarification detail: split by newline + dash into bullet list.
  if (label === "Clarification detail" && value.includes("\n- ")) {
    const items = value
      .split("\n")
      .map((line) => line.replace(/^- /, "").trim())
      .filter(Boolean);

    return (
      <ul className="list-disc pl-4 space-y-1">
        {items.map((item) => (
          <li key={item} className="text-muted-foreground">
            {item}
          </li>
        ))}
      </ul>
    );
  }

  // Preprocessing actions: split by comma into display tags.
  if (label === "Preprocessing actions" && value.includes(",")) {
    const items = value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    return (
      <div className="flex flex-wrap gap-1 mt-1">
        {items.map((item) => (
          <span
            key={item}
            className="rounded border bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
          >
            {item}
          </span>
        ))}
      </div>
    );
  }

  // Top candidates: split by semicolon into bullet list.
  if (label === "Top candidates" && value.includes(";")) {
    const items = value
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean);

    return (
      <ul className="list-disc pl-4 space-y-1">
        {items.map((item) => (
          <li key={item} className="text-muted-foreground">
            {item}
          </li>
        ))}
      </ul>
    );
  }

  // Default: render as plain text with whitespace preserved.
  return <span className="text-muted-foreground whitespace-pre-wrap">{value}</span>;
}

// TraceDetails
//
// Component that displays trace event metadata in a formatted grid.
// Renders key-value pairs with special formatting applied by formatTraceValue().

function TraceDetails({ details }: { details?: Record<string, string> }) {
  // Skip rendering if no details provided.
  if (!details || Object.keys(details).length === 0) {
    return null;
  }

  return (
    <div className="mt-2 rounded-md border bg-muted/40 p-3">
      <div className="space-y-2">
        {/* Each detail: label as header, value formatted by formatTraceValue(). */}
        {Object.entries(details).map(([label, value]) => (
          <div key={label} className="text-xs">
            <div className="font-medium">{label}</div>
            <div>{formatTraceValue(label, value)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Timeline
//
// Renders a vertical timeline of trace events with a connecting line.
// Each event is a card showing timestamp, outcome, event type, component, and details.

function Timeline({ events }: { events: TraceEvent[] }) {
  return (
    <div className="relative space-y-0">
      {/* Vertical connecting line. */}
      <div className="absolute left-[19px] top-2 bottom-2 w-0.5 bg-border" />
      {/* Timeline event cards. */}
      {events.map((e, i) => (
        <div key={i} className="relative flex gap-4 pb-6">
          <div className="relative z-10 mt-1.5">
            <div className="w-3 h-3 rounded-full bg-primary border-2 border-background" />
          </div>

          {/* Event card: timestamp, outcome status, type, component, summary, and details. */}
          <Card className="flex-1">
            <CardContent className="p-4 space-y-1">
              {/* Header row: timestamp, outcome badge, event type. */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground">
                  {safeFormatDate(e.timestamp)}
                </span>
                <StatusBadge status={e.outcome} />
                <span className="text-xs font-medium">{e.eventType || 'N/A'}</span>
              </div>

              {/* Component name that generated this event. */}
              <p className="text-xs text-muted-foreground">
                Component: {e.component || 'N/A'}
              </p>

              {/* Reason code (if applicable, e.g., for failures). */}
              {e.reasonCode && <p className="text-xs">Reason: {e.reasonCode}</p>}

              {/* Safe summary prioritized over raw summary/message. */}
              <p className="text-sm">{e.safeSummary || e.summary || e.message || 'N/A'}</p>
              {/* Additional details rendered with special formatting. */}
              <TraceDetails details={e.details} />
            </CardContent>
          </Card>
        </div>
      ))}
    </div>
  );
}

// Traces
//
// Admin page for tracing request flow through the system. Search by correlation ID
// (tracks a single request across all backend services) or session ID (tracks all
// requests from a single patient session). Displays events in chronological order
// with component, outcome, and contextual details.

export default function TracesPage() {
  // Extract initial search params from URL (populated by Bookings page links).
  const [searchParams] = useSearchParams();

  const initialCorrelationId = searchParams.get('correlationId') || '';
  const initialSessionId = searchParams.get('sessionId') || '';

  // Input field states for correlation and session ID searches.
  const [correlationId, setCorrelationId] = useState(initialCorrelationId);
  const [sessionId, setSessionId] = useState(initialSessionId);

  // Determine initial search type and value based on URL params.
  const initialSearchType =
    initialCorrelationId ? 'correlation' : initialSessionId ? 'session' : null;
  const initialSearchValue = initialCorrelationId || initialSessionId;

  // Current active search: 'correlation' fetches by correlation ID, 'session' by session ID.
  const [searchType, setSearchType] = useState<'correlation' | 'session' | null>(
    initialSearchType,
  );
  // Current search value being used to fetch events.
  const [searchValue, setSearchValue] = useState(initialSearchValue);

  const { data, loading, error, refetch } = useApiCall(
    (api) => {
      if (searchType === 'correlation' && searchValue) {
        return api.getTracesByCorrelationId(searchValue);
      }
      if (searchType === 'session' && searchValue) {
        return api.getTracesBySessionId(searchValue);
      }
      return Promise.resolve({ data: [] as TraceEvent[], requestCorrelationId: '' });
    },
    [searchType, searchValue],
  );

  // Handler for correlation ID search button or Enter key.
  const searchByCorrelation = () => {
    if (correlationId) {
      setSearchType('correlation');
      setSearchValue(correlationId);
    }
  };

  // Handler for session ID search button or Enter key.
  const searchBySession = () => {
    if (sessionId) {
      setSearchType('session');
      setSearchValue(sessionId);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Traces</h2>

      {/* Search inputs for correlation ID and session ID. */}
      <div className="flex flex-wrap gap-3 items-end">
        {/* Correlation ID search: tracks single request across all services. */}
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Correlation ID"
              value={correlationId}
              onChange={(e) => setCorrelationId(e.target.value)}
              className="pl-9 w-[280px] h-9"
              onKeyDown={(e) => e.key === 'Enter' && searchByCorrelation()}
            />
          </div>
          <Button size="sm" onClick={searchByCorrelation}>
            Search
          </Button>
        </div>

        {/* Session ID search: tracks all requests from one patient session. */}
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Patient Session ID"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              className="pl-9 w-[280px] h-9"
              onKeyDown={(e) => e.key === 'Enter' && searchBySession()}
            />
          </div>
          <Button size="sm" onClick={searchBySession}>
            Search
          </Button>
        </div>
      </div>

      {/* Display active search ID with copy button. */}
      {searchValue && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            Showing trace for:{' '}
            <code className="font-mono">{searchValue.slice(0, 12)}…</code>
          </span>
          <CopyButton text={searchValue} />
        </div>
      )}

      {/* Loading and error states. */}
      {loading && <Skeleton className="h-48" />}
      {error && <ErrorBanner error={error} onRetry={refetch} />}
      {/* No results message. */}
      {data && data.length === 0 && searchValue && (
        <p className="text-muted-foreground text-sm">No trace events found.</p>
      )}
      {/* Prompt to start searching. */}
      {!searchValue && (
        <p className="text-muted-foreground text-sm">
          Enter a Correlation ID or Patient Session ID to view trace events.
        </p>
      )}
      {/* Timeline of events. */}
      {data && data.length > 0 && <Timeline events={data} />}
    </div>
  );
}