import { useState } from "react";
import { Loader2, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { chatRenewalIdentify } from "@/lib/api-client";
import { toast } from "sonner";

function responseToMessage(res: any) {
  return {
    role: "assistant" as const,
    text: res.userMessage,
    quickReplies: res.quickReplies ?? undefined,
    selectionLists: res.selectionLists ?? undefined,
    needsClarification: res.needsClarification ?? undefined,
    isChronicContinuity: res.isChronicContinuity ?? undefined,
    showConsentNotice: res.showConsentNotice ?? undefined,
    bookingReferenceId: res.bookingReferenceId ?? undefined,
    confirmationType: res.confirmationType ?? undefined,
    confirmationSummary: res.confirmationSummary ?? undefined,
  };
}

export default function ChatWidgetRenewalIdentity() {
  const [nationalId, setNationalId] = useState("");
  const [loading, setLoading] = useState(false);

  const {
    addMessage,
    setStep,
    setPatientNationalId,
  } = useBookingFlow();

  const handleContinue = async () => {
    if (!nationalId.trim()) {
      toast.error("Enter your National ID first.");
      return;
    }

    setLoading(true);

    try {
      const res = await chatRenewalIdentify(nationalId.trim());
      setPatientNationalId(nationalId.trim());
      addMessage(responseToMessage(res));
      setStep("chat");
    } catch (err: any) {
      toast.error(err.message || "Failed to retrieve renewal medications.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      <h3 className="font-semibold text-sm mb-3">Renew Medication</h3>

      <p className="text-xs text-muted-foreground mb-3">
        Enter your National ID / Iqama / Border ID to retrieve your active medications.
      </p>

      <Input
        value={nationalId}
        onChange={(e) => setNationalId(e.target.value)}
        placeholder="National ID / Iqama / Border ID"
        className="h-8 text-xs mb-3"
        disabled={loading}
      />

      <Button
        size="sm"
        className="w-full h-8 text-xs"
        onClick={handleContinue}
        disabled={loading || !nationalId.trim()}
      >
        {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
        Retrieve Medications
      </Button>

      <Button
        variant="ghost"
        size="sm"
        className="w-full text-xs justify-start mt-3"
        onClick={() => setStep("chat")}
      >
        <ChevronLeft className="h-3 w-3 mr-1" />
        Back
      </Button>
    </div>
  );
}