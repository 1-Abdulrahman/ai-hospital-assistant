import { CheckCircle, Package } from "lucide-react";
import type { ConfirmationSummary } from "@/lib/types";

// Props for the confirmation card component
interface ConfirmationCardProps {
  // Distinguishes whether this confirmation is for an appointment or a medication renewal
  confirmationType?: "appointment" | "renewal";
  // Structured summary returned by backend containing display-friendly fields
  confirmationSummary?: ConfirmationSummary;
  // Fallback message text to show when `confirmationSummary` is not available
  messageText?: string;
}

/**
 * ConfirmationCard
 *
 * Renders a compact, structured confirmation summary when the backend
 * returns a `confirmationSummary`. If the structured summary is missing but
 * a plain `messageText` is provided, the component will render the text as
 * a fallback. Important safety note: do not attempt to parse or extract
 * identifiers from freeform `messageText` — only use explicit fields from
 * `confirmationSummary` for display and downstream logic.
 */
export default function ConfirmationCard({ confirmationType, confirmationSummary, messageText }: ConfirmationCardProps) {
  // If there is no structured summary, fall back to showing the raw message
  // (keeps UI resilient when server returns human-readable text-only responses)
  if (!confirmationSummary) {
    return messageText ? <p className="text-xs whitespace-pre-wrap">{messageText}</p> : null;
  }

  // Determine whether this is a renewal (affects iconography and title)
  const isRenewal = confirmationType === "renewal";
  const Icon = isRenewal ? Package : CheckCircle;

  return (
    <div className="mt-2 rounded-lg border border-border bg-accent/30 p-3">
      {/* Header: icon and title */}
      <div className="flex items-center gap-2 mb-2">
        <div className={`flex h-8 w-8 items-center justify-center rounded-full ${isRenewal ? "bg-secondary/10" : "bg-[hsl(var(--success))]/10"}`}>
          <Icon className={`h-4 w-4 ${isRenewal ? "text-secondary" : "text-[hsl(var(--success))]"}`} />
        </div>
        <h4 className="text-xs font-semibold">
          {isRenewal ? "Renewal Confirmed" : "Booking Confirmed"}
        </h4>
      </div>

      {/* Summary fields: render only fields that are present in the structured summary */}
      <div className="space-y-1 text-[11px]">
        {/* Booking reference (human-facing short code) */}
        {confirmationSummary.bookingReferenceId && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Booking Ref</span>
            <span className="font-mono font-medium">{confirmationSummary.bookingReferenceId}</span>
          </div>
        )}

        {/* Correlation ID: technical identifier for debugging — styled monospace and allowed to break */}
        {confirmationSummary.correlationId && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Correlation ID</span>
            <span className="font-mono font-medium text-[10px] break-all">{confirmationSummary.correlationId}</span>
          </div>
        )}

        {/* Human-friendly labels: specialty, doctor name, date, and slot */}
        {confirmationSummary.specialtyLabel && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Specialty</span>
            <span className="font-medium capitalize">{confirmationSummary.specialtyLabel}</span>
          </div>
        )}

        {confirmationSummary.doctorLabel && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Doctor</span>
            <span className="font-medium">{confirmationSummary.doctorLabel}</span>
          </div>
        )}

        {confirmationSummary.date && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Date</span>
            <span className="font-medium">{confirmationSummary.date}</span>
          </div>
        )}

        {confirmationSummary.slotLabel && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Slot</span>
            <span className="font-medium">{confirmationSummary.slotLabel}</span>
          </div>
        )}

        {/* Renewal-specific label: medication name for renewals */}
        {confirmationSummary.renewalItemLabel && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Medication</span>
            <span className="font-medium">{confirmationSummary.renewalItemLabel}</span>
          </div>
        )}

        {/* Optional FHIR Task reference: technical identifier that may be used for downstream APIs */}
        {confirmationSummary.refillTaskRef && (
          <div className="flex justify-between gap-3">
            <span className="text-muted-foreground">FHIR Task</span>
            <span className="font-mono font-medium text-[10px] break-all text-right">
              {confirmationSummary.refillTaskRef}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
