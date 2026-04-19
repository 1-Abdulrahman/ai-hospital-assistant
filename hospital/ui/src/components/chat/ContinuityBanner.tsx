import { Stethoscope } from "lucide-react";
import type { ContinuityPayload } from "@/lib/types";

interface ContinuityBannerProps {
  continuity: ContinuityPayload;
}

function buildContinuityMessage(continuity: ContinuityPayload): string {
  const doctor = continuity.preferredPractitionerDisplay || "your previous physician";

  if (continuity.matched && continuity.preferredPractitionerHasAvailability === true) {
    return `${doctor} has been prioritized and currently has availability.`;
  }

  if (continuity.matched && continuity.preferredPractitionerHasAvailability === false) {
    return `${doctor} was recognized as your previous physician, but there is no matching availability right now. Showing other available doctors.`;
  }

  if (continuity.matched) {
    return `${doctor} has been prioritized when available.`;
  }

  return continuity.message || "No same-specialty continuity-of-care match was found. Showing all available doctors.";
}

export default function ContinuityBanner({ continuity }: ContinuityBannerProps) {
  return (
    <div className="mt-2 flex items-start gap-2 rounded-md border border-border bg-accent/40 px-2.5 py-2 text-[11px]">
      <Stethoscope className="h-3 w-3 text-primary mt-0.5 shrink-0" />
      <p className="flex-1 text-accent-foreground">
        ⚕️ {buildContinuityMessage(continuity)}
      </p>
    </div>
  );
}