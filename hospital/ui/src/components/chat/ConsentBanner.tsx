// Small, dismissible informational banner used to request user consent
// for sharing health information during the booking flow.
//
// Notes:
// - The banner is intentionally simple and non-modal: it gives context but does
//   not block the user's ability to continue. The UI pattern mirrors common
//   in-app consent notices for short-lived flows like appointment booking.
// - Dismissal is stored in local component state (not persisted). If you need
//   persistent dismissal across sessions, move this into higher-level state
//   or localStorage.
import { useState } from "react";
import { Info, X } from "lucide-react";

// Component: ConsentBanner
// Renders a small informational banner with an icon, consent text, and a
// dismiss (X) button. The `dismissed` flag is stored locally so the banner
// disappears after the user closes it during this session.
export default function ConsentBanner() {
  // Local dismissed flag: when true the banner is removed from the DOM.
  // This is intentionally ephemeral; it does not persist across page reloads.
  const [dismissed, setDismissed] = useState(false);

  // If user has dismissed the banner, render nothing.
  if (dismissed) return null;

  return (
    <div className="mt-2 flex items-start gap-2 rounded-md border border-border bg-accent/40 px-2.5 py-2 text-[11px]">
      {/* Decorative/informational icon on the left */}
      <Info className="h-3 w-3 text-primary mt-0.5 shrink-0" />

      {/* Message body: concise consent text. Keep language short and actionable. */}
      <p className="flex-1 text-accent-foreground">
        By continuing, you consent to share health information for appointment scheduling.
      </p>

      {/*
        Dismiss button: visually unobtrusive, only controls local UI state.
        - `aria-label` would be added here for screen reader clarity if needed
        - Using a native <button> keeps keyboard accessibility and focus behavior
      */}
      <button
        onClick={() => setDismissed(true)}
        className="shrink-0 text-muted-foreground hover:text-foreground"
        aria-label="Dismiss consent notice"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
