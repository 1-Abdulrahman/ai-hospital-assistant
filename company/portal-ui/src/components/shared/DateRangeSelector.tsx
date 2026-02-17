import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { format, subDays } from 'date-fns';

export type DatePreset = 'today' | '7d' | '30d' | 'custom';

interface DateRangeSelectorProps {
  from: string;
  to: string;
  onChange: (from: string, to: string, preset: DatePreset) => void;
  preset: DatePreset;
}

export function DateRangeSelector({ from, to, onChange, preset }: DateRangeSelectorProps) {
  const today = format(new Date(), 'yyyy-MM-dd');

  const handlePreset = (value: string) => {
    const p = value as DatePreset;
    const t = today;
    switch (p) {
      case 'today': onChange(t, t, p); break;
      case '7d': onChange(format(subDays(new Date(), 7), 'yyyy-MM-dd'), t, p); break;
      case '30d': onChange(format(subDays(new Date(), 30), 'yyyy-MM-dd'), t, p); break;
      default: break;
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Select value={preset} onValueChange={handlePreset}>
        <SelectTrigger className="w-[160px] h-9">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="today">Today</SelectItem>
          <SelectItem value="7d">Last 7 days</SelectItem>
          <SelectItem value="30d">Last 30 days</SelectItem>
          <SelectItem value="custom">Custom range</SelectItem>
        </SelectContent>
      </Select>
      {preset === 'custom' && (
        <>
          <input type="date" value={from} onChange={(e) => onChange(e.target.value, to, 'custom')} className="h-9 rounded-md border bg-background px-3 text-sm" />
          <span className="text-muted-foreground text-sm">to</span>
          <input type="date" value={to} onChange={(e) => onChange(from, e.target.value, 'custom')} className="h-9 rounded-md border bg-background px-3 text-sm" />
        </>
      )}
    </div>
  );
}
