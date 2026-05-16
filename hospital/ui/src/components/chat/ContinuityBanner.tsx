// Icon used to represent continuity-of-care / primary clinician
import { Stethoscope } from "lucide-react";

// Payload type describing continuity-of-care lookup results returned by backend
import type { ContinuityPayload } from "@/lib/types";

// Props for ContinuityBanner component
interface ContinuityBannerProps {
  // Continuity lookup result object which may contain:
  // - matched: whether a same-specialty continuity match was found
  // - preferredPractitionerDisplay: human-friendly practitioner name
  // - preferredPractitionerHasAvailability: optional bool indicating if that practitioner has open slots
  // - message: optional fallback message from backend
  continuity: ContinuityPayload;
}

// Build a concise, human-readable message from the continuity payload.
// The function centralizes logic for wording so the UI remains consistent
// across different continuity scenarios and can be tested independently.
//
// Behavior summary:
// - If a preferred practitioner was matched and has availability => explicit prioritized + available message
// - If matched but no availability => explain we recognized the previous physician but will show alternatives
// - If matched but availability unknown => indicate prioritization when available
// - Otherwise use backend-provided message or a sensible default
function buildContinuityMessage(continuity: ContinuityPayload): string {
  // Friendly display name for the matched practitioner, falling back to generic text
  const doctor = continuity.preferredPractitionerDisplay || "your previous physician";

  // Matched and explicitly available
  if (continuity.matched && continuity.preferredPractitionerHasAvailability === true) {
    return `${doctor} has been prioritized and currently has availability.`;
  }

  // Matched but explicitly has no availability
  if (continuity.matched && continuity.preferredPractitionerHasAvailability === false) {
    return `${doctor} was recognized as your previous physician, but there is no matching availability right now. Showing other available doctors.`;
  }

  // Matched but availability not specified (server didn't return explicit availability flag)
  if (continuity.matched) {
    return `${doctor} has been prioritized when available.`;
  }

  // Fallback: prefer server-provided message when available, otherwise a generic notice
  return continuity.message || "No same-specialty continuity-of-care match was found. Showing all available doctors.";
}

// Small banner component shown above doctor availability results when the
// system detects (or attempts to detect) continuity-of-care for the patient.
//
// Purpose:
// - Communicate to the user when we attempted to prioritize their previous
//   clinician and whether that clinician currently has open appointment slots.
// - Provide friendly wording that explains why the UI may prioritize one
//   doctor or fall back to other providers.
export default function ContinuityBanner({ continuity }: ContinuityBannerProps) {
  return (
    // Accessible banner container: small compact layout used inside side panels
    <div className="mt-2 flex items-start gap-2 rounded-md border border-border bg-accent/40 px-2.5 py-2 text-[11px]">
      {/* Decorative icon indicating clinical continuity */}
      <Stethoscope className="h-3 w-3 text-primary mt-0.5 shrink-0" />

      {/* Message body: small text with the built continuity message. The ⚕️ emoji
          is used as a lightweight visual affordance; the text itself is generated
          by `buildContinuityMessage` to centralize phrasing logic. */}
      <p className="flex-1 text-accent-foreground">
        ⚕️ {buildContinuityMessage(continuity)}
      </p>
    </div>
  );
}
