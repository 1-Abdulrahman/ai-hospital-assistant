import { CheckCircle, Package } from "lucide-react";
import type { ConfirmationSummary } from "@/lib/types";

interface ConfirmationCardProps {
  confirmationType?: "appointment" | "renewal";
  confirmationSummary?: ConfirmationSummary;
  messageText?: string;
}

/**
 * Renders a structured confirmation card using confirmationSummary fields.
 * Safety: if confirmationSummary is missing but confirmationType exists, fallback to messageText.
 * Never parses identifiers from messageText.
 */
export default function ConfirmationCard({ confirmationType, confirmationSummary, messageText }: ConfirmationCardProps) {
  if (!confirmationSummary) {
    // Fallback: render messageText only when summary is absent
    return messageText ? <p className="text-xs whitespace-pre-wrap">{messageText}</p> : null;
  }

  const isRenewal = confirmationType === "renewal";
  const Icon = isRenewal ? Package : CheckCircle;

  return (
    <div className="mt-2 rounded-lg border border-border bg-accent/30 p-3">
      <div className="flex items-center gap-2 mb-2">
        <div className={`flex h-8 w-8 items-center justify-center rounded-full ${isRenewal ? "bg-secondary/10" : "bg-[hsl(var(--success))]/10"}`}>
          <Icon className={`h-4 w-4 ${isRenewal ? "text-secondary" : "text-[hsl(var(--success))]"}`} />
        </div>
        <h4 className="text-xs font-semibold">
          {isRenewal ? "Renewal Confirmed" : "Booking Confirmed"}
        </h4>
      </div>
      <div className="space-y-1 text-[11px]">
        {confirmationSummary.bookingReferenceId && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Booking Ref</span>
            <span className="font-mono font-medium">{confirmationSummary.bookingReferenceId}</span>
          </div>
        )}
        {confirmationSummary.correlationId && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Correlation ID</span>
            <span className="font-mono font-medium text-[10px] break-all">{confirmationSummary.correlationId}</span>
          </div>
        )}
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
        {confirmationSummary.renewalItemLabel && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Medication</span>
            <span className="font-medium">{confirmationSummary.renewalItemLabel}</span>
          </div>
        )}
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
