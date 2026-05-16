import { useState } from "react";
import { Loader2, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { chatContinuityIdentify, chatSelection } from "@/lib/api-client";
import { toast } from "sonner";

/**
 * Transforms the API response into a standardized message format for the chat interface.
 * Extracts relevant fields from the backend response and normalizes undefined values.
 *
 * @param res - The API response object containing user message and metadata
 * @returns A formatted message object with role "assistant" and structured metadata
 */
function responseToMessage(res: any) {
  return {
    role: "assistant" as const,
    text: res.userMessage,
    quickReplies: res.quickReplies ?? undefined,
    selectionLists: res.selectionLists ?? undefined,
    needsClarification: res.needsClarification ?? undefined,
    isChronicContinuity: res.isChronicContinuity ?? undefined,
    continuity: res.continuity ?? undefined,
    showConsentNotice: res.showConsentNotice ?? undefined,
    requiresContinuityIdentity: res.requiresContinuityIdentity ?? undefined,
    bookingReferenceId: res.bookingReferenceId ?? undefined,
    confirmationType: res.confirmationType ?? undefined,
    confirmationSummary: res.confirmationSummary ?? undefined,
  };
}

/**
 * ChatWidgetContinuityIdentity Component
 *
 * Allows patients to enter their National ID/Iqama/Border ID to check for continuity of care
 * with previous physicians. If a match is found, the system will prioritize the previous physician.
 * Patients can also skip this check to view all available slots.
 *
 * @component
 */
export default function ChatWidgetContinuityIdentity() {
  const [nationalId, setNationalId] = useState("");
  const [loading, setLoading] = useState(false);

  const { addMessage, setStep, setPatientNationalId } = useBookingFlow();

  /**
   * Handles the continuity check by submitting the patient's National ID to the backend.
   * On success, stores the ID and transitions to the chat step with the API response.
   * On error, displays a toast notification.
   */
  const handleContinue = async () => {
    if (!nationalId.trim()) {
      toast.error("Enter your National ID first.");
      return;
    }

    setLoading(true);

    try {
      const res = await chatContinuityIdentify(nationalId.trim());
      setPatientNationalId(nationalId.trim());
      addMessage(responseToMessage(res));
      setStep("chat");
    } catch (err: any) {
      toast.error(err.message || "Failed to check continuity of care.");
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handles skipping the continuity check by sending a skip action to the backend.
   * This allows the patient to proceed to the chat without checking for previous physicians.
   * On success, transitions to the chat step with all available slots.
   * On error, displays a toast notification.
   */
  const handleSkip = async () => {
    setLoading(true);

    try {
      const res = await chatSelection({
        selectionType: "continuity",
        selectionId: "skip",
        selectionValue: "skip",
        action: "SKIP_CONTINUITY_CHECK",
      });
      addMessage(responseToMessage(res));
      setStep("chat");
    } catch (err: any) {
      toast.error(err.message || "Failed to skip continuity of care.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      {/* Section heading */}
      <h3 className="font-semibold text-sm mb-3">Continuity of Care</h3>

      {/* Helper text explaining what continuity of care is and why it matters */}
      <p className="text-xs text-muted-foreground mb-3">
        Enter your National ID / Iqama / Border ID to prioritize continuity of care when a matching previous physician exists.
      </p>

      {/* Input field for patient's national identification number */}
      <Input
        value={nationalId}
        onChange={(e) => setNationalId(e.target.value)}
        placeholder="National ID / Iqama / Border ID"
        className="h-8 text-xs mb-3"
        disabled={loading}
      />

      {/* Primary action: Submit national ID for continuity check */}
      <Button
        size="sm"
        className="w-full h-8 text-xs"
        onClick={handleContinue}
        disabled={loading || !nationalId.trim()}
      >
        {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
        Check Continuity of Care
      </Button>

      {/* Secondary action: Skip continuity check and show all available slots */}
      <Button
        variant="outline"
        size="sm"
        className="w-full h-8 text-xs mt-2"
        onClick={handleSkip}
        disabled={loading}
      >
        Skip and Show All Slots
      </Button>

      {/* Navigation: Go back to chat step */}
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