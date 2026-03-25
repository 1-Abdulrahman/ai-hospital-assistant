import { Stethoscope } from "lucide-react";

/**
 * Non-dismissible info banner rendered when isChronicContinuity is true.
 * Shows previous physician priority message.
 */
export default function ContinuityBanner() {
  return (
    <div className="mt-2 flex items-start gap-2 rounded-md border border-border bg-accent/40 px-2.5 py-2 text-[11px]">
      <Stethoscope className="h-3 w-3 text-primary mt-0.5 shrink-0" />
      <p className="flex-1 text-accent-foreground">
        ⚕️ As a returning patient, your previous physician will be prioritized when available.
      </p>
    </div>
  );
}
