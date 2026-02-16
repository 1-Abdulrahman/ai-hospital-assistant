import { useEffect, useState } from "react";
import { CheckCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { confirmBooking } from "@/lib/api-client";
import { toast } from "sonner";
import { useWidgetState } from "@/hooks/use-widget-state";

export default function ChatWidgetConfirm() {
  const { otpVerified, selectedDate, selectedSlotId, selectedSpecialty, bookingId, correlationId, setBookingResult, reset } = useBookingFlow();
  const { setIsOpen } = useWidgetState();
  const [loading, setLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(!!bookingId);

  useEffect(() => {
    if (!otpVerified) {
      reset();
    }
  }, [otpVerified, reset]);

  const handleConfirm = async () => {
    setLoading(true);
    try {
      const res = await confirmBooking({
        date: selectedDate || "",
        slotId: selectedSlotId || "",
        specialtyId: selectedSpecialty || undefined,
      });
      setBookingResult(res.bookingId, res.correlationId);
      setConfirmed(true);
      toast.success("Booking confirmed!");
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleNewBooking = () => {
    reset();
    setIsOpen(false);
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      {confirmed ? (
        <>
          <div className="flex justify-center mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[hsl(var(--success))]/10">
              <CheckCircle className="h-5 w-5 text-[hsl(var(--success))]" />
            </div>
          </div>
          <h3 className="font-semibold text-sm text-center mb-3">Booking Confirmed</h3>
          <div className="space-y-1.5 rounded-lg bg-muted px-3 py-2.5 text-xs mb-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Booking ID</span>
              <span className="font-mono font-medium text-[11px]">{bookingId}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Correlation ID</span>
              <span className="font-mono font-medium text-[10px] break-all">{correlationId}</span>
            </div>
            {selectedDate && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Date</span>
                <span className="font-medium">{selectedDate}</span>
              </div>
            )}
          </div>
          <Button size="sm" className="w-full h-8 text-xs" onClick={handleNewBooking}>
            Start New Booking
          </Button>
        </>
      ) : (
        <>
          <h3 className="font-semibold text-sm mb-3">Confirm Booking</h3>
          <div className="space-y-1.5 rounded-lg bg-muted px-3 py-2.5 text-xs mb-3">
            {selectedSpecialty && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Specialty</span>
                <span className="font-medium capitalize">{selectedSpecialty}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Date</span>
              <span className="font-medium">{selectedDate}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Slot</span>
              <span className="font-medium">{selectedSlotId}</span>
            </div>
          </div>
          <Button size="sm" className="w-full h-8 text-xs" onClick={handleConfirm} disabled={loading}>
            {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            Confirm Booking
          </Button>
        </>
      )}
    </div>
  );
}
