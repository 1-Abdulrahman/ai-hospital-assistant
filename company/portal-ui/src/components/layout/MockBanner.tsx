import { getIsMockMode } from '@/api/apiClient';

export function MockBanner() {
  if (!getIsMockMode()) return null;
  return (
    <div className="bg-destructive text-destructive-foreground text-center py-2 px-4 text-sm font-semibold">
      ⚠ MOCK DATA MODE – NOT CONNECTED TO BACKEND
    </div>
  );
}
