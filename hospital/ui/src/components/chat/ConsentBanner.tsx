import { useState } from "react";
import { Info, X } from "lucide-react";

/**
 * Dismissible info banner rendered when showConsentNotice is true.
 * Close button stores dismissal in local component state.
 */
export default function ConsentBanner() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div className="mt-2 flex items-start gap-2 rounded-md border border-border bg-accent/40 px-2.5 py-2 text-[11px]">
      <Info className="h-3 w-3 text-primary mt-0.5 shrink-0" />
      <p className="flex-1 text-accent-foreground">
        By continuing, you consent to share health information for appointment scheduling.
      </p>
      <button onClick={() => setDismissed(true)} className="shrink-0 text-muted-foreground hover:text-foreground">
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
