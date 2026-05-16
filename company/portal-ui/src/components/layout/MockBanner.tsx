import { Button } from '@/components/ui/button';
import { getApiMode, setApiMode, type ApiMode } from '@/api/apiClient';

function nextMode(current: ApiMode): ApiMode {
  return current === 'mock' ? 'real' : 'mock';
}

export function MockBanner() {
  const currentMode = getApiMode();
  const isMock = currentMode === 'mock';

  const handleToggle = () => {
    const next = nextMode(currentMode);
    setApiMode(next);

    const url = new URL(window.location.href);
    url.searchParams.set('mock', next === 'mock' ? '1' : '0');
    window.location.href = url.toString();
  };

  return (
    <div
      className={
        isMock
          ? 'bg-destructive text-destructive-foreground'
          : 'bg-emerald-700 text-white'
      }
    >
      <div className="mx-auto flex max-w-screen-2xl items-center justify-between gap-3 px-4 py-2 text-sm">
        <div className="font-semibold">
          {isMock
            ? '⚠ MOCK DATA MODE — Future portal preview, not connected to backend'
            : '✅ REAL BACKEND MODE — Connected to the live local backend'}
        </div>

        <Button
          variant="secondary"
          size="sm"
          className="h-7 text-xs"
          onClick={handleToggle}
        >
          Switch to {isMock ? 'Real backend' : 'Mock preview'}
        </Button>
      </div>
    </div>
  );
}