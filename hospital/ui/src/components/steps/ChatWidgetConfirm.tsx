import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { chatConfirm } from "@/lib/api-client";
import { toast } from "sonner";

export default function ChatWidgetConfirm() {
  const {
    selectedSpecialtyId,
    selectedDoctorId,
    selectedSlotId,
    selectedDate,
    patientNationalId,
    patientEmail,
    addMessage,
    setStep,
    resetFlow,
  } = useBookingFlow();
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    if (!patientNationalId || !patientEmail) {
      toast.error("National ID and email are required before confirmation.");
      return;
    }

    setLoading(true);
    try {
      const res = await chatConfirm({
        action: "CONFIRM_APPOINTMENT",
        specialtyId: selectedSpecialtyId || undefined,
        doctorId: selectedDoctorId || undefined,
        slotId: selectedSlotId || undefined,
        date: selectedDate || undefined,
        nationalId: patientNationalId,
        email: patientEmail,
      });
      addMessage({
        role: "assistant",
        text: res.userMessage,
        confirmationType: res.confirmationType,
        confirmationSummary: res.confirmationSummary,
        bookingReferenceId: res.bookingReferenceId,
      });
      if (res.errors?.length) {
        toast.error(res.errors[0].userMessage);
        setStep("chat");
      } else {
        setStep("done");
        toast.success("Booking confirmed!");
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      <h3 className="font-semibold text-sm mb-3">Confirm Booking</h3>
      <div className="space-y-1.5 rounded-lg bg-muted px-3 py-2.5 text-xs mb-3">
        {selectedSpecialtyId && (
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">Specialty</span>
            <span className="font-medium capitalize text-right">{selectedSpecialtyId}</span>
          </div>
        )}
        {selectedDoctorId && (
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">Doctor</span>
            <span className="font-medium text-right">{selectedDoctorId}</span>
          </div>
        )}
        {selectedDate && (
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">Date</span>
            <span className="font-medium text-right">{selectedDate}</span>
          </div>
        )}
        {selectedSlotId && (
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">Slot</span>
            <span className="font-medium text-right break-all">{selectedSlotId}</span>
          </div>
        )}
        {patientEmail && (
          <div className="flex justify-between gap-2">
            <span className="text-muted-foreground">Email</span>
            <span className="font-medium text-right">{patientEmail}</span>
          </div>
        )}
      </div>
      <Button size="sm" className="w-full h-8 text-xs" onClick={handleConfirm} disabled={loading}>
        {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
        Confirm Booking
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="w-full text-xs justify-start mt-3"
        onClick={resetFlow}
      >
        Cancel
      </Button>
    </div>
  );
}