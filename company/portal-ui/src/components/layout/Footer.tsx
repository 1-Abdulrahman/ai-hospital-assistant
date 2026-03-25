import { getIsMockMode } from '@/api/apiClient';

export function Footer() {
  const mode = getIsMockMode() ? 'MOCK DATA' : 'REAL BACKEND';
  return (
    <footer className="h-8 border-t bg-card flex items-center justify-center text-xs text-muted-foreground">
      Architecture Mode: {mode}
    </footer>
  );
}
