import { format, parseISO } from 'date-fns';

export function safeFormatDate(isoString: string | undefined | null, fmt = 'yyyy-MM-dd HH:mm:ss'): string {
  if (!isoString) return 'N/A';
  try {
    const date = parseISO(isoString);
    if (isNaN(date.getTime())) return 'N/A';
    return format(date, fmt);
  } catch {
    return 'N/A';
  }
}

export function safeFormatShortDate(isoString: string | undefined | null): string {
  return safeFormatDate(isoString, 'yyyy-MM-dd');
}
