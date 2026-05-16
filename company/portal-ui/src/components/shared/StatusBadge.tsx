import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const variants: Record<string, string> = {
  OK: 'bg-emerald-500/15 text-emerald-700 border-emerald-300',
  SUCCESS: 'bg-emerald-500/15 text-emerald-700 border-emerald-300',
  COMPLETED: 'bg-emerald-500/15 text-emerald-700 border-emerald-300',
  ACTIVE: 'bg-emerald-500/15 text-emerald-700 border-emerald-300',

  INFO: 'bg-slate-500/10 text-slate-700 border-slate-300',

  DEGRADED: 'bg-amber-500/15 text-amber-700 border-amber-300',
  WARNING: 'bg-amber-500/15 text-amber-700 border-amber-300',

  DOWN: 'bg-red-500/15 text-red-700 border-red-300',
  FAILED: 'bg-red-500/15 text-red-700 border-red-300',
  FAILURE: 'bg-red-500/15 text-red-700 border-red-300',
  ERROR: 'bg-red-500/15 text-red-700 border-red-300',

  DROPPED: 'bg-orange-500/15 text-orange-700 border-orange-300',
};

export function StatusBadge({ status }: { status: string | undefined }) {
  const s = status?.toUpperCase() || 'N/A';

  return (
    <Badge variant="outline" className={cn('text-xs', variants[s] || '')}>
      {s}
    </Badge>
  );
}