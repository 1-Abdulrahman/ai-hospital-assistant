// UI components from the shadcn/ui library
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

// API client function to submit confirmation to the backend
import { chatConfirm } from "@/lib/api-client";

// Hook to access booking/chat flow state and actions
import { useBookingFlow } from "@/hooks/use-booking-flow";

// Type definitions for API responses
import type { ChatResponse } from "@/lib/types";

// Toast notification library for displaying success/error messages
import { toast } from "sonner";

// Normalize backend confirmation response into the message format used by the chat UI.
// This converts API response fields into the shape expected by the message display system.
// Uses nullish coalescing to provide undefined for optional fields not in the response.
function responseToMessage(res: ChatResponse) {
  return {
    role: "assistant" as const,
    text: res.userMessage,
    quickReplies: res.quickReplies ?? undefined,
    selectionLists: res.selectionLists ?? undefined,
    needsClarification: res.needsClarification ?? undefined,
    isChronicContinuity: res.isChronicContinuity ?? undefined,
    continuity: res.continuity ?? undefined,
    requiresContinuityIdentity: res.requiresContinuityIdentity ?? undefined,
    showConsentNotice: res.showConsentNotice ?? undefined,
    bookingReferenceId: res.bookingReferenceId ?? undefined,
    confirmationType: res.confirmationType ?? undefined,
    confirmationSummary: res.confirmationSummary ?? undefined,
  };
}

// Convert specialty ID to human-readable label.
// Example: "CARDIOLOGY" or "cardiology" → "Cardiology"
// Example: "GENERAL_PRACTICE" → "General Practice"
// Returns "Not selected" if value is empty or null.
function humanizeSpecialty(value: string | null | undefined): string {
  if (!value) return "Not selected";
  // Replace underscores with spaces, trim, and capitalize each word
  return value.replace(/_/g, " ").trim().replace(/\b\w/g, (c) => c.toUpperCase());
}

// Format UTC date string into user-friendly local time display.
// Converts ISO format (e.g., "2024-05-15T14:30:00Z") to readable format:
// Example output: "May 15, 2024, 2:30 PM EDT"
// If parsing fails, returns the original value as fallback.
function formatUtcDate(value: string | null | undefined): string {
  if (!value) return "Not selected";

  // Parse ISO date string
  const parsed = new Date(value);
  
  // If parsing failed (invalid date), return original value
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  // Format using browser's locale with time zone information
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

// Validate email address format using a simple regex pattern.
// Checks for: non-whitespace chars @ non-whitespace chars . non-whitespace chars
// Examples: valid@example.com ✓, invalid.email ✗, @example.com ✗
// Returns false for null/undefined or empty strings.
function isValidEmail(value: string | null | undefined): boolean {
  if (!value) return false;
  // Simple email regex: user@domain.extension
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

// Final confirmation screen: displays booking/renewal details and confirms with backend.
// Shown after OTP verification step. Allows user to review selections before submitting.
// For appointments: shows specialty, doctor, date, time slot
// For renewals: shows medication and email
export default function ChatWidgetConfirm() {
  // Extract all booking state and actions from the shared booking flow hook
  const {
    // Current flow mode: "appointment", "direct", or "renewal"
    currentMode,
    // Selected appointment details (for non-renewal flows)
    selectedSpecialtyId,
    selectedSpecialtyLabel,
    selectedDoctorLabel,
    selectedDate,
    selectedSlotId,
    selectedSlotLabel,
    selectedSlotStartUtc,
    // Selected medication (for renewal flow)
    renewalItemId,
    renewalItemLabel,
    // Patient information collected during flow
    patientNationalId,
    patientEmail,
    // Loading and messaging state
    isLoading,
    addMessage,
    setStep,
    setLoading,
    setError,
  } = useBookingFlow();

  // Compute display labels from booking state, with fallbacks if needed
  
  // Specialty display: use user-set label or humanize the ID
  const specialtyLabel =
    selectedSpecialtyLabel || humanizeSpecialty(selectedSpecialtyId);

  // Doctor display: fall back to "Not available" if not set
  const doctorLabel = selectedDoctorLabel || "Not available";

  // Date/time display: format UTC date for user's timezone
  // Prefers slot start time over just the date if available
  const appointmentDateLabel = formatUtcDate(
    selectedSlotStartUtc || selectedDate,
  );

  // Slot display: use label if available, otherwise try ID, fallback to "Not selected"
  const slotLabel = selectedSlotLabel || selectedSlotId || "Not selected";
  
  // Medication display: use label if available, otherwise ID or "Not selected"
  const medicationLabel = renewalItemLabel || renewalItemId || "Not selected";

  // Validate email format for display warning and button enable state
  const emailValid = isValidEmail(patientEmail);

  // Validation logic for appointment confirmation.
  // All of these must be true to enable the confirm button:
  // - Specialty and slot selected
  // - Patient ID and email provided
  // - Email has valid format
  const canConfirmAppointment =
    Boolean(selectedSpecialtyId) &&
    Boolean(selectedSlotId) &&
    Boolean(patientNationalId) &&
    Boolean(patientEmail) &&
    emailValid;

  // Validation logic for renewal confirmation.
  // All of these must be true to enable the confirm button:
  // - Medication selected
  // - Patient ID and email provided
  // - Email has valid format
  const canConfirmRenewal =
    Boolean(renewalItemId) &&
    Boolean(patientNationalId) &&
    Boolean(patientEmail) &&
    emailValid;

  // Use appropriate validation based on current mode
  const canConfirm =
    currentMode === "renewal" ? canConfirmRenewal : canConfirmAppointment;

  // Handler for the confirm button.
  // Performs validation, calls backend API, and handles response/errors.
  const handleConfirm = async () => {
    // Validation: check all required fields are present
    
    if (!patientNationalId) {
      toast.error("National ID is missing.");
      return;
    }

    if (!patientEmail) {
      toast.error("Email is missing.");
      return;
    }

    if (!emailValid) {
      toast.error("Please enter a valid email address.");
      return;
    }

    // Mode-specific validation
    if (currentMode === "renewal" && !renewalItemId) {
      toast.error("Medication selection is missing.");
      return;
    }

    if (currentMode !== "renewal" && (!selectedSpecialtyId || !selectedSlotId)) {
      toast.error("Specialty or slot selection is missing.");
      return;
    }

    // Show loading state
    setLoading(true);
    setError(null);

    try {
      // Call appropriate API endpoint based on current mode
      // Renewal flow: confirm medication renewal with patient info
      // Appointment flow: confirm appointment with specialty, slot, and patient info
      const res =
        currentMode === "renewal"
          ? await chatConfirm({
              action: "CONFIRM_RENEWAL",
              nationalId: patientNationalId,
              email: patientEmail,
              renewalItemId: renewalItemId!,
            })
          : await chatConfirm({
              action: "CONFIRM_APPOINTMENT",
              specialtyId: selectedSpecialtyId!,
              slotId: selectedSlotId!,
              nationalId: patientNationalId,
              email: patientEmail,
            });

      // Add backend's response to chat history
      addMessage(responseToMessage(res));

      // Check if backend returned errors
      if (res.errors?.length) {
        // Show first error message to user
        toast.error(res.errors[0].userMessage);
      } else {
        // Success: move to final "done" step
        setStep("done");
      }
    } catch (err: any) {
      // Network or parsing error: show error message
      toast.error(err.message || "Confirmation failed.");
    } finally {
      // Always clear loading state
      setLoading(false);
    }
  };

  // Handler for cancel/back button.
  // Returns user to the OTP verification step so they can change their email/phone.
  const handleBack = () => {
    setStep("otp");
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      {/* Header: title changes based on current mode (renewal vs appointment) */}
      <h3 className="font-semibold text-sm mb-3">
        {currentMode === "renewal" ? "Confirm Renewal" : "Confirm Booking"}
      </h3>

      {/* Summary card: displays mode-specific confirmation details */}
      <Card className="p-4 bg-muted">
        {/* Renewal mode: show medication and email */}
        {currentMode === "renewal" ? (
          <div className="space-y-3 text-sm">
            {/* Medication being renewed */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Medication</span>
              <span className="font-medium break-words">{medicationLabel}</span>
            </div>

            {/* Patient email for renewal confirmation */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium break-words">{patientEmail || "Not provided"}</span>
            </div>
          </div>
        ) : (
          /* Appointment mode: show specialty, doctor, date, time slot, and email */
          <div className="space-y-3 text-sm">
            {/* Medical specialty selected */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Specialty</span>
              <span className="font-medium break-words">{specialtyLabel}</span>
            </div>

            {/* Doctor/practitioner assigned to the slot */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Doctor</span>
              <span className="font-medium break-words">{doctorLabel}</span>
            </div>

            {/* Appointment date formatted in local timezone */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Date</span>
              <span className="font-medium break-words">{appointmentDateLabel}</span>
            </div>

            {/* Time slot label */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Slot</span>
              <span className="font-medium break-words">{slotLabel}</span>
            </div>

            {/* Patient email for appointment confirmation */}
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium break-words">{patientEmail || "Not provided"}</span>
            </div>
          </div>
        )}
      </Card>

      {/* Email validation error: shown if email format is invalid but email was provided */}
      {!emailValid && patientEmail && (
        <p className="text-xs text-destructive mt-2">
          The email address format looks invalid. Please go back and correct it.
        </p>
      )}

      {/* Confirm button: submits booking/renewal when all validation passes */}
      <Button
        className="mt-4 w-full"
        onClick={handleConfirm}
        disabled={isLoading || !canConfirm}  // Disabled while loading or validation fails
      >
        {isLoading ? "Confirming..." : currentMode === "renewal" ? "Confirm Renewal" : "Confirm Booking"}
      </Button>

      {/* Back/Cancel button: returns to OTP step to change email/phone */}
      <Button
        variant="ghost"
        className="mt-2 w-full"
        onClick={handleBack}
        disabled={isLoading}
      >
        Cancel
      </Button>
    </div>
  );
}
