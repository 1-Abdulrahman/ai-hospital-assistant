import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { chatConfirm } from "@/lib/api-client";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import type { ChatResponse } from "@/lib/types";
import { toast } from "sonner";

function responseToMessage(res: ChatResponse) {
  return {
    role: "assistant" as const,
    text: res.userMessage,
    quickReplies: res.quickReplies ?? undefined,
    selectionLists: res.selectionLists ?? undefined,
    needsClarification: res.needsClarification ?? undefined,
    isChronicContinuity: res.isChronicContinuity ?? undefined,
    requiresContinuityIdentity: res.requiresContinuityIdentity ?? undefined,
    showConsentNotice: res.showConsentNotice ?? undefined,
    bookingReferenceId: res.bookingReferenceId ?? undefined,
    confirmationType: res.confirmationType ?? undefined,
    confirmationSummary: res.confirmationSummary ?? undefined,
  };
}

function humanizeSpecialty(value: string | null | undefined): string {
  if (!value) return "Not selected";
  return value.replace(/_/g, " ").trim().replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatUtcDate(value: string | null | undefined): string {
  if (!value) return "Not selected";

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function isValidEmail(value: string | null | undefined): boolean {
  if (!value) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export default function ChatWidgetConfirm() {
  const {
    currentMode,
    selectedSpecialtyId,
    selectedSpecialtyLabel,
    selectedDoctorLabel,
    selectedDate,
    selectedSlotId,
    selectedSlotLabel,
    selectedSlotStartUtc,
    renewalItemId,
    renewalItemLabel,
    patientNationalId,
    patientEmail,
    isLoading,
    addMessage,
    setStep,
    setLoading,
    setError,
  } = useBookingFlow();

  const specialtyLabel =
    selectedSpecialtyLabel || humanizeSpecialty(selectedSpecialtyId);

  const doctorLabel = selectedDoctorLabel || "Not available";

  const appointmentDateLabel = formatUtcDate(
    selectedSlotStartUtc || selectedDate,
  );

  const slotLabel = selectedSlotLabel || selectedSlotId || "Not selected";
  const medicationLabel = renewalItemLabel || renewalItemId || "Not selected";

  const emailValid = isValidEmail(patientEmail);

  const canConfirmAppointment =
    Boolean(selectedSpecialtyId) &&
    Boolean(selectedSlotId) &&
    Boolean(patientNationalId) &&
    Boolean(patientEmail) &&
    emailValid;

  const canConfirmRenewal =
    Boolean(renewalItemId) &&
    Boolean(patientNationalId) &&
    Boolean(patientEmail) &&
    emailValid;

  const canConfirm =
    currentMode === "renewal" ? canConfirmRenewal : canConfirmAppointment;

  const handleConfirm = async () => {
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

    if (currentMode === "renewal" && !renewalItemId) {
      toast.error("Medication selection is missing.");
      return;
    }

    if (currentMode !== "renewal" && (!selectedSpecialtyId || !selectedSlotId)) {
      toast.error("Specialty or slot selection is missing.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
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

      addMessage(responseToMessage(res));

      if (res.errors?.length) {
        toast.error(res.errors[0].userMessage);
      } else {
        setStep("done");
      }
    } catch (err: any) {
      toast.error(err.message || "Confirmation failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setStep("otp");
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      <h3 className="font-semibold text-sm mb-3">
        {currentMode === "renewal" ? "Confirm Renewal" : "Confirm Booking"}
      </h3>

      <Card className="p-4 bg-muted">
        {currentMode === "renewal" ? (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Medication</span>
              <span className="font-medium break-words">{medicationLabel}</span>
            </div>

            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium break-words">{patientEmail || "Not provided"}</span>
            </div>
          </div>
        ) : (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Specialty</span>
              <span className="font-medium break-words">{specialtyLabel}</span>
            </div>

            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Doctor</span>
              <span className="font-medium break-words">{doctorLabel}</span>
            </div>

            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Date</span>
              <span className="font-medium break-words">{appointmentDateLabel}</span>
            </div>

            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Slot</span>
              <span className="font-medium break-words">{slotLabel}</span>
            </div>

            <div className="grid grid-cols-[90px_1fr] gap-2">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium break-words">{patientEmail || "Not provided"}</span>
            </div>
          </div>
        )}
      </Card>

      {!emailValid && patientEmail && (
        <p className="text-xs text-destructive mt-2">
          The email address format looks invalid. Please go back and correct it.
        </p>
      )}

      <Button
        className="mt-4 w-full"
        onClick={handleConfirm}
        disabled={isLoading || !canConfirm}
      >
        {isLoading ? "Confirming..." : currentMode === "renewal" ? "Confirm Renewal" : "Confirm Booking"}
      </Button>

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
