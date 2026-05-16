// React hooks for state management
import { useState } from "react";

// Icons from lucide-react
// Loader2: spinning animation for loading state
// ChevronLeft: left arrow for back navigation button
import { Loader2, ChevronLeft } from "lucide-react";

// UI components from shadcn/ui library
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// Hook to access booking flow state and actions
import { useBookingFlow } from "@/hooks/use-booking-flow";

// API function to identify patient by national ID and retrieve their renewal medications
import { chatRenewalIdentify } from "@/lib/api-client";

// Toast notification library for displaying success/error messages to user
import { toast } from "sonner";

// Transform API response into standardized chat message format.
// Normalizes backend response fields into message object shape for consistent UI rendering.
// Extracts all optional fields from response (quick replies, selections, special flags) and sets to undefined if missing.
function responseToMessage(res: any) {
  return {
    // Assistant role identifies this as a bot message (not user-sent)
    role: "assistant" as const,
    // Main message text to display in chat
    text: res.userMessage,
    // Quick reply buttons (e.g., "Yes", "No", or next step prompts)
    quickReplies: res.quickReplies ?? undefined,
    // Selection lists (dropdown, multi-select, medication list, etc.)
    selectionLists: res.selectionLists ?? undefined,
    // Flag: indicates if more information is needed from user
    needsClarification: res.needsClarification ?? undefined,
    // Flag: indicates chronic medication continuity flow (long-term medications)
    isChronicContinuity: res.isChronicContinuity ?? undefined,
    // Continuity information (if applicable)
    continuity: res.continuity ?? undefined,
    // Flag: show consent notice before proceeding
    showConsentNotice: res.showConsentNotice ?? undefined,
    // Booking reference ID (if appointment/renewal was already created)
    bookingReferenceId: res.bookingReferenceId ?? undefined,
    // Confirmation type (if this response includes a confirmation)
    confirmationType: res.confirmationType ?? undefined,
    // Confirmation summary details (if confirmation included)
    confirmationSummary: res.confirmationSummary ?? undefined,
  };
}

// Identity verification step for medication renewal flow.
// User enters their national ID to retrieve active medications from their medical record.
// Once identified, transitions to chat to display available medications for renewal selection.
export default function ChatWidgetRenewalIdentity() {
  // Local state: national ID entered by user
  const [nationalId, setNationalId] = useState("");
  
  // Track if API call is in progress (disables input and button)
  const [loading, setLoading] = useState(false);

  // Extract booking flow state and actions
  const {
    // Add message to chat history (for backend response)
    addMessage,
    // Navigate to next flow step
    setStep,
    // Save patient national ID to booking state
    setPatientNationalId,
  } = useBookingFlow();

  // Handler for "Retrieve Medications" button.
  // Validates national ID, calls backend to identify patient and fetch their active medications,
  // then transitions to chat to display medication list for selection.
  const handleContinue = async () => {
    // Validation: ensure national ID was entered
    if (!nationalId.trim()) {
      toast.error("Enter your National ID first.");
      return;
    }

    // Show loading state
    setLoading(true);

    try {
      // Call backend to identify patient by national ID and retrieve their active medications
      const res = await chatRenewalIdentify(nationalId.trim());
      
      // Save national ID to booking flow state for use in OTP verification later
      setPatientNationalId(nationalId.trim());
      
      // Transform backend response to chat message format and add to message history
      addMessage(responseToMessage(res));
      
      // Move to chat step to display medications and handle selection
      setStep("chat");
    } catch (err: any) {
      // Show error if patient identification or medication retrieval failed
      toast.error(err.message || "Failed to retrieve renewal medications.");
    } finally {
      // Always clear loading state
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      {/* Header: step title */}
      <h3 className="font-semibold text-sm mb-3">Renew Medication</h3>

      {/* Instructions: explain what user needs to do */}
      <p className="text-xs text-muted-foreground mb-3">
        Enter your National ID / Iqama / Border ID to retrieve your active medications.
      </p>

      {/* National ID input: identifies which patient to look up */}
      <Input
        value={nationalId}
        onChange={(e) => setNationalId(e.target.value)}
        placeholder="National ID / Iqama / Border ID"
        className="h-8 text-xs mb-3"
        // Disable input while API call is in progress
        disabled={loading}
      />

      {/* Primary button: retrieves patient's active medications */}
      <Button
        size="sm"
        className="w-full h-8 text-xs"
        onClick={handleContinue}
        // Disable if loading or no national ID entered
        disabled={loading || !nationalId.trim()}
      >
        {/* Show spinning loader while fetching from backend */}
        {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
        Retrieve Medications
      </Button>

      {/* Back button: returns to chat to restart or go back to main flow */}
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