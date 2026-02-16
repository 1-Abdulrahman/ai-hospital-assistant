import { useState } from "react";
import { format } from "date-fns";
import { CalendarIcon, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { cn } from "@/lib/utils";

const DEMO_SLOTS = [
  { id: "slot-09", label: "09:00 AM" },
  { id: "slot-10", label: "10:00 AM" },
  { id: "slot-11", label: "11:00 AM" },
  { id: "slot-14", label: "02:00 PM" },
  { id: "slot-15", label: "03:00 PM" },
  { id: "slot-16", label: "04:00 PM" },
];

export default function ChatWidgetBook() {
  const [date, setDate] = useState<Date>();
  const [slotId, setSlotId] = useState("");
  const { selectedSpecialty, setSelectedDate, setSelectedSlotId, setStep } = useBookingFlow();

  const handleContinue = () => {
    if (!date || !slotId) return;
    setSelectedDate(format(date, "yyyy-MM-dd"));
    setSelectedSlotId(slotId);
    setStep("otp");
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      <h3 className="font-semibold text-sm mb-1">Schedule Appointment</h3>
      {selectedSpecialty && (
        <p className="text-xs text-muted-foreground mb-3 capitalize">
          Specialty: {selectedSpecialty}
        </p>
      )}

      <div className="space-y-3">
        <div className="space-y-1.5">
          <label className="text-xs font-medium">Date</label>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className={cn(
                  "w-full justify-start text-left font-normal h-8 text-xs",
                  !date && "text-muted-foreground"
                )}
              >
                <CalendarIcon className="mr-2 h-3 w-3" />
                {date ? format(date, "PPP") : "Pick a date"}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={date}
                onSelect={setDate}
                disabled={(d) => d < new Date()}
                initialFocus
                className={cn("p-3 pointer-events-auto")}
              />
            </PopoverContent>
          </Popover>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium">Time Slot</label>
          <Select value={slotId} onValueChange={setSlotId}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder="Select time" />
            </SelectTrigger>
            <SelectContent>
              {DEMO_SLOTS.map((s) => (
                <SelectItem key={s.id} value={s.id}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button className="w-full h-8 text-xs" onClick={handleContinue} disabled={!date || !slotId}>
          Continue to Verification
        </Button>
      </div>

      <Button
        variant="ghost"
        size="sm"
        className="w-full text-xs justify-start mt-3"
        onClick={() => setStep("chat")}
      >
        <ChevronLeft className="h-3 w-3 mr-1" />
        Back to chat
      </Button>
    </div>
  );
}
