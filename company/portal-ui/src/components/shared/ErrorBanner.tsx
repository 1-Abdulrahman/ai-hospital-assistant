import { AlertCircle, RefreshCw, Copy, Check } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import type { ApiError } from '@/api/types';

function CopyId({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <span className="inline-flex items-center gap-1 text-xs font-mono">
      {label}: {value.slice(0, 8)}…
      <button onClick={copy} className="hover:text-foreground" title="Copy">
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      </button>
    </span>
  );
}

interface ErrorBannerProps {
  error: ApiError;
  onRetry?: () => void;
}

export function ErrorBanner({ error, onRetry }: ErrorBannerProps) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Error</AlertTitle>
      <AlertDescription className="flex flex-col gap-2">
        <p>{error.userMessage}</p>
        <div className="flex flex-wrap gap-3">
          <CopyId label="Request ID" value={error.requestCorrelationId} />
          {error.backendCorrelationId && (
            <CopyId label="Backend ID" value={error.backendCorrelationId} />
          )}
        </div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry} className="w-fit mt-1">
            <RefreshCw className="h-3 w-3 mr-1" /> Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
