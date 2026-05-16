import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Calendar, Pill, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import {
  sendChatMessage,
  chatDirectStart,
  chatRenewalRequest,
  chatSelection,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type {
  ChatResponse,
  ChatMessage,
  QuickReply,
  SelectionListItem,
} from "@/lib/types";
import SelectionList from "./chat/SelectionList";
import ConsentBanner from "./chat/ConsentBanner";
import ContinuityBanner from "./chat/ContinuityBanner";
import ConfirmationCard from "./chat/ConfirmationCard";
import ChatWidgetOtp from "./steps/ChatWidgetOtp";
import ChatWidgetConfirm from "./steps/ChatWidgetConfirm";
import ChatWidgetRenewalIdentity from "./steps/ChatWidgetRenewalIdentity";
import ChatWidgetContinuityIdentity from "./steps/ChatWidgetContinuityIdentity";

// ChatWidgetContent: main chat UI used by hospital portal.
// - Manages local input state and scroll position
// - Uses `useBookingFlow` hook for shared booking/chat state and actions
// - Handles user actions: sending text, choosing modes, selections, quick replies
// - Renders a sequence of messages and conditional step screens (otp/identity/confirm)

// Normalize backend chat responses into the message shape consumed by the UI.
// This keeps the render loop simple and avoids scattering response parsing
// logic across the component.
// 
// The backend returns different field names for optional data; this function
// extracts what's needed and uses nullish coalescing to provide undefined for
// optional fields that weren't included in the response.
function responseToMessage(res: ChatResponse) {
  return {
    // All assistant messages have role="assistant"
    role: "assistant" as const,
    // The main message text to display in the chat
    text: res.userMessage,
    // Quick reply buttons shown below the message
    quickReplies: res.quickReplies ?? undefined,
    // Lists of selectable items (specialty, doctor, slot, medication)
    selectionLists: res.selectionLists ?? undefined,
    // Whether backend wants user to provide more detail on their complaint
    needsClarification: res.needsClarification ?? undefined,
    // Whether this is a chronic continuity case (continuing patient)
    isChronicContinuity: res.isChronicContinuity ?? undefined,
    // Continuity matching result from the backend
    continuity: res.continuity ?? undefined,
    // Whether user must verify they're a continuing patient
    requiresContinuityIdentity: res.requiresContinuityIdentity ?? undefined,
    // Whether to show consent notice to user
    showConsentNotice: res.showConsentNotice ?? undefined,
    // Reference ID for the booking (for tracking purposes)
    bookingReferenceId: res.bookingReferenceId ?? undefined,
    // Type of confirmation (appointment, renewal, etc.)
    confirmationType: res.confirmationType ?? undefined,
    // Summary data to show in confirmation screen
    confirmationSummary: res.confirmationSummary ?? undefined,
  };
}

export default function ChatWidgetContent() {
  // Local state for user text input field
  const [input, setInput] = useState("");
  
  // Ref to the scrollable message container - used to auto-scroll to newest messages
  const scrollRef = useRef<HTMLDivElement>(null);
  
  // Ref to the input field - used to focus when complaint mode is selected
  const inputRef = useRef<HTMLInputElement>(null);
  
  // Flag to track if backend is asking for more detail on the user's complaint.
  // When true, the placeholder text changes to guide the user to provide clarification.
  const [awaitingClarificationDetail, setAwaitingClarificationDetail] = useState(false);

  // Hook that provides all shared booking/chat flow state and actions.
  // This is the single source of truth for:
  // - Current booking step (complaint, identity verification, otp, confirmation, etc.)
  // - Chat messages history
  // - Selected appointment/medication details
  // - Loading and error states
  const {
    // Current step in the booking/verification flow
    step,
    // Array of chat messages (both user and assistant)
    messages,
    // Current booking mode: "complaint", "direct", or "renewal"
    currentMode,
    // Whether an API call is in progress
    isLoading,
    // IDs of selected items for the booking
    selectedSpecialtyId,
    selectedDoctorId,
    selectedSlotId,
    renewalItemId,
    // Actions to modify booking state
    addMessage,
    setStep,
    setCurrentMode,
    setLoading,
    setError,
    setSelectedSpecialtyId,
    setSelectedDoctorId,
    setSelectedSlotId,
    setSelectedDate,
    setRenewalItemId,
    resetFlow,
    // Actions to set display labels for selected items
    setSelectedSpecialtyLabel,
    setSelectedDoctorLabel,
    setSelectedSlotLabel,
    setSelectedSlotStartUtc,
    setRenewalItemLabel,
  } = useBookingFlow();

  // Auto-scroll to bottom when messages change so newest content is visible.
  // Uses smooth scrolling for better UX. Triggered every time messages array changes.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,  // Scroll to the absolute bottom
      behavior: "smooth",  // Animate the scroll smoothly
    });
  }, [messages]);  // Re-run whenever messages array changes



  // Utility function to display errors from API responses as toast notifications.
  // If backend returns error details, shows the first error message to the user
  // and logs the reason code for debugging.
  const handleResponseErrors = (res: ChatResponse) => {
    if (res.errors?.length) {
      // Display the user-friendly error message as a toast
      toast.error(res.errors[0].userMessage);
      // Log the technical reason code for debugging
      console.debug("[API reasonCode]", res.errors[0].reasonCode);
    }
  };

  // Handler for when user sends a chat message (complaint, clarification, etc.).
  // Flow: validate input → add to messages → call API → process response → update UI
  // If backend needs more detail, flag it so placeholder text guides next input.
  const handleSend = async () => {
    // Trim whitespace from input
    const text = input.trim();
    // Exit early if no text or already loading (prevent duplicate submissions)
    if (!text || isLoading) return;

    // Clear input field and add user message to chat history
    setInput("");
    addMessage({ role: "user", text });
    // Show loading spinner
    setLoading(true);
    setError(null);

    try {
      // Send message to backend; it returns next step in conversation
      const res = await sendChatMessage(text);
      // Add assistant's response to chat history
      addMessage(responseToMessage(res));
      // Display any backend errors as toast
      handleResponseErrors(res);
      // Update clarification flag if backend wants more detail on the complaint
      setAwaitingClarificationDetail(Boolean(res.needsClarification));
    } catch (err: any) {
      // If API call fails, show error message in chat
      addMessage({
        role: "assistant",
        text: err.message || "An error occurred.",
      });
    } finally {
      // Always stop loading spinner whether request succeeded or failed
      setLoading(false);
    }
  };


  // Mode starter: handles three entry modes for different booking flows.
  // - "complaint": User describes symptoms → specialty selection → doctor/slot booking
  //   Just focuses input; no server call needed yet.
  // - "direct": User books appointment directly without describing symptoms.
  //   Calls chatDirectStart() to get initial specialty list from the backend.
  // - "renewal": User requests medication renewal.
  //   Calls chatRenewalRequest() to begin the renewal flow.
  //   After medication selection, transitions to "renewal_identity" step for verification.
  const handleModeStart = async (mode: "complaint" | "direct" | "renewal") => {
    setCurrentMode(mode);

    // For "complaint" mode, just focus the input and return immediately
    // (no server call needed; user will type their symptoms)
    if (mode === "complaint") {
      inputRef.current?.focus();
      return;
    }

    // For "direct" and "renewal" modes, make server call to begin the flow
    setLoading(true);

    try {
      // Call appropriate API endpoint based on mode
      const res =
        mode === "direct"
          ? await chatDirectStart()    // Get specialty list for direct booking
          : await chatRenewalRequest(); // Get renewal flow initialization

      addMessage(responseToMessage(res));
      handleResponseErrors(res);

      // For renewal mode, immediately transition to identity verification step
      // (user must verify identity before selecting a medication to renew)
      if (mode === "renewal") {
        setStep("renewal_identity");
      }
    } catch (err: any) {
      addMessage({
        role: "assistant",
        text: err.message || "An error occurred.",
      });
    } finally {
      setLoading(false);
    }
  };



  // Handler for when user selects an item from a selection list
  // (specialty, doctor, time slot, medication, date).
  // Updates local state immediately for UI responsiveness, then confirms with backend.
  const handleSelection = async (listType: string, item: SelectionListItem) => {
    // Map selection type to backend action name
    const actionMap: Record<string, string> = {
      specialty: "SELECT_SPECIALTY",
      doctor: "SELECT_DOCTOR",
      slot: "SELECT_SLOT",
      date: "SELECT_DATE",
      medication: "SELECT_MEDICATION_FOR_RENEWAL",
    };

    // Update local state immediately so UI shows selection right away
    // (this keeps the widget feeling responsive even before API returns)
    
    if (listType === "specialty") {
      // User selected a medical specialty (e.g., Cardiology)
      setSelectedSpecialtyId(item.id);
      setSelectedSpecialtyLabel(item.label);
    }

    if (listType === "doctor") {
      // User selected a doctor/practitioner
      setSelectedDoctorId(item.id);
      setSelectedDoctorLabel(item.label);
    }

    if (listType === "slot") {
      // User selected a specific time slot for appointment
      setSelectedSlotId(item.id);
      setSelectedSlotLabel(item.label);
      // Extract doctor name from slot metadata (sometimes in separate field)
      setSelectedDoctorLabel(
        item.meta?.practitionerDisplay ??
          item.label.split("•")[0]?.trim() ??
          null,
      );
      // Store the appointment date/time in UTC format
      setSelectedSlotStartUtc(item.meta?.isoDate ?? null);
      // Store the date separately for display purposes
      if (item.meta?.dateKey) {
        setSelectedDate(item.meta.dateKey);
      } else if (item.meta?.isoDate) {
        setSelectedDate(item.meta.isoDate);
      }
    }

    if (listType === "medication") {
      // User selected a medication to renew
      setRenewalItemId(item.id);
      setRenewalItemLabel(item.label);
    }
    
    // Show loading spinner while confirming selection with backend
    setLoading(true);

    try {
      // Notify backend of the user's selection
      const res = await chatSelection({
        selectionType: listType,
        selectionId: item.id,
        selectionValue: item.label,
        action: actionMap[listType] || listType.toUpperCase(),
      });

      // Add backend's response to chat
      addMessage(responseToMessage(res));
      handleResponseErrors(res);

      // If appointment booking requires verification of patient continuity with provider
      if (res.requiresContinuityIdentity) {
        setStep("continuity_identity");
        return;
      }

      // Check if backend returned any errors
      const hasBackendErrors = Boolean(res.errors?.length);

      // For medication renewal: after medication selection, move to OTP verification step
      // (only if no errors occurred)
      if (
        currentMode === "renewal" &&
        listType === "medication" &&
        !hasBackendErrors
      ) {
        setStep("otp");
      }
    } catch (err: any) {
      // Show API error in chat
      addMessage({
        role: "assistant",
        text: err.message || "An error occurred.",
      });
    } finally {
      // Stop loading spinner
      setLoading(false);
    }
  };

  // Selections flow: when the user picks a specialty/doctor/slot/medication
  // we update booking state locally then inform the backend which may
  // respond with next steps (OTP, continuity identity, confirmation, etc.).

  // Handler for when user clicks a quick reply button.
  // Quick replies can either prompt for more text input or send a predefined value to the API.
  const handleQuickReply = async (qr: QuickReply) => {
    // Check if this quick reply should prompt for additional user input
    if (qr.action === "PROMPT_FOR_TEXT") {
      // Show the quick reply label as a user message
      addMessage({ role: "user", text: qr.label });
      // Explain to user that they should provide more detail
      addMessage({
        role: "assistant",
        text: "Please type a little more detail. I will combine it with your earlier complaint before checking the specialty again.",
      });
      // Set flag so placeholder tells user to provide clarification
      setAwaitingClarificationDetail(true);
      // Focus input field so user can immediately type
      inputRef.current?.focus();
      return;
    }

    // For regular quick replies, add the value as a user message
    addMessage({ role: "user", text: qr.value });
    // Show loading spinner
    setLoading(true);

    try {
      // Send the quick reply value to the backend (as if user typed it)
      const res = await sendChatMessage(qr.value);
      // Add backend's response
      addMessage(responseToMessage(res));
      handleResponseErrors(res);
      // Check if backend is asking for more clarification
      setAwaitingClarificationDetail(Boolean(res.needsClarification));
    } catch (err: any) {
      // Show error in chat
      addMessage({
        role: "assistant",
        text: err.message || "An error occurred.",
      });
    } finally {
      // Stop loading spinner
      setLoading(false);
    }
  };

  // Quick replies either prompt for more text or send the selected value
  // back to the server as if the user had typed it.

  // Render full-screen step components when in special flow states.
  // These screens replace the entire chat interface (no message list shown):
  // - renewal_identity: User verifies their identity before renewing medication
  // - continuity_identity: User verifies they're a continuing patient of the doctor
  // - otp: One-time password verification step
  // - confirm: Final confirmation of booking/renewal
  if (step === "renewal_identity") return <ChatWidgetRenewalIdentity />;
  if (step === "continuity_identity") return <ChatWidgetContinuityIdentity />;
  if (step === "otp") return <ChatWidgetOtp />;
  if (step === "confirm") return <ChatWidgetConfirm />;

  // Render special step screens early so the main chat list is not mounted
  // during identity/otp flows.

  const firstConsentIndex = messages.findIndex((msg) => msg.showConsentNotice);

  return (
    <div className="flex flex-col h-full">
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-3"
      >
        {/* Initial welcome screen shown when no messages and no mode selected yet */}
        {messages.length === 0 && !currentMode && (
          <div className="flex flex-col items-center justify-center pt-8 text-center">
            {/* Welcome icon */}
            <div className="mb-3 rounded-full bg-accent p-3">
              <Calendar className="h-6 w-6 text-primary" />
            </div>

            {/* Welcome heading */}
            <h2 className="text-base font-semibold">How can we help?</h2>

            {/* Instructions to select a mode */}
            <p className="mt-1 text-xs text-muted-foreground px-2">
              Choose an option to get started.
            </p>

            <div className="mt-4 flex flex-col gap-2 w-full max-w-[220px]">
              {/* Mode 1: Complaint-based booking. User describes symptoms,
                  backend suggests specialty, user selects doctor/slot. */}
              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs gap-2"
                onClick={() => handleModeStart("complaint")}
              >
                <Stethoscope className="h-3.5 w-3.5" />
                Describe Symptoms
              </Button>

              {/* Mode 2: Direct booking. Skip symptom description and go straight
                  to selecting a specialty, then doctor and time slot. */}
              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs gap-2"
                onClick={() => handleModeStart("direct")}
              >
                <Calendar className="h-3.5 w-3.5" />
                Schedule Directly
              </Button>

              {/* Mode 3: Medication renewal. User selects medication to renew,
                  verifies identity (OTP), and completes the renewal request. */}
              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs gap-2"
                onClick={() => handleModeStart("renewal")}
              >
                <Pill className="h-3.5 w-3.5" />
                Medication Renewal
              </Button>
            </div>
          </div>
        )}

        {/* Chat message history: display all user and assistant messages */}
        {messages.map((msg, idx) => (
          <div
            key={msg.id}
            className={cn(
              "flex flex-col",
              // Align user messages to right, assistant messages to left
              msg.role === "user" ? "items-end" : "items-start"
            )}
          >
            {/* Message bubble: styled differently for user (blue) vs assistant (gray) */}
            <Card
              className={cn(
                "max-w-[85%] px-3 py-2 text-xs",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground border-primary"  // User messages: blue
                  : "bg-muted"  // Assistant messages: gray
              )}
            >
              <p className="whitespace-pre-wrap">{msg.text}</p>
            </Card>

            {/* Assistant-only components: banners and interactive elements */}
            {msg.role === "assistant" && (
              <>
                {/* Consent notice banner: shown once when user first books */}
                {msg.showConsentNotice && idx === firstConsentIndex && (
                  <ConsentBanner />
                )}

                {/* Continuity banner: shows if user is a continuing patient of the doctor */}
                {msg.continuity ? (
                  <ContinuityBanner continuity={msg.continuity} />
                ) : msg.isChronicContinuity ? (
                  <ContinuityBanner
                    continuity={{
                      matched: true,
                      message: "Your previous physician will be prioritized when available.",
                    }}
                  />
                ) : null}

                {/* Confirmation card: summary of booking/renewal before final confirmation */}
                {msg.confirmationSummary && (
                  <ConfirmationCard
                    confirmationType={msg.confirmationType}
                    confirmationSummary={msg.confirmationSummary}
                    messageText={msg.text}
                  />
                )}

                {/* Selection lists: specialty, doctor, time slot, or medication options */}
                {msg.selectionLists?.map((list, listIdx) => (
                  <SelectionList
                    key={`${list.type}-${listIdx}`}
                    list={list}
                    onSelect={(item) => handleSelection(list.type, item)}
                    selectedId={
                      list.type === "specialty"
                        ? selectedSpecialtyId
                        : list.type === "doctor"
                        ? selectedDoctorId
                        : list.type === "slot"
                        ? selectedSlotId
                        : list.type === "medication"
                        ? renewalItemId
                        : null
                    }
                    disabled={isLoading}
                  />
                ))}

                {/* Continue button: shown after user selects a time slot */}
                {msg.selectionLists?.some((l) => l.type === "slot") &&
                  selectedSlotId && (
                    <Button
                      size="sm"
                      className="mt-2 w-full h-8 text-xs"
                      onClick={() => setStep("otp")}
                    >
                      Continue to Verification
                    </Button>
                  )}

                {/* Quick reply buttons: suggested responses or next steps */}
                {msg.quickReplies && msg.quickReplies.length > 0 && (
                  <div className="mt-2 flex flex-col gap-1 max-w-[85%]">
                    {/* Helper text when backend needs more detail on complaint */}
                    {msg.needsClarification && (
                      <p className="text-[11px] text-muted-foreground">
                        Tap below to add more detail, or choose one of the suggested specialties.
                      </p>
                    )}

                    {/* Render each quick reply as a clickable button */}
                    {msg.quickReplies.map((qr) => (
                      <Button
                        key={`${qr.label}-${qr.value}`}
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => handleQuickReply(qr)}
                        disabled={isLoading}
                      >
                        {qr.label}
                      </Button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ))}

        {/* Loading indicator: spinning icon shown while waiting for API response */}
        {isLoading && (
          <div className="flex justify-start">
            <Card className="bg-muted px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </Card>
          </div>
        )}

        {/* Success screen: shown after booking/renewal is complete */}
        {step === "done" && (
          <div className="flex justify-center pt-2">
            <Button
              size="sm"
              variant="outline"
              className="text-xs"
              onClick={resetFlow}
            >
              Start New Booking
            </Button>
          </div>
        )}
      </div>

      {/* Message input form: hidden when booking is complete */}
      {step !== "done" && (
        <form
          className="flex gap-2 border-t px-4 py-2 shrink-0"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          {/* Text input field: user types complaints, clarifications, or responses */}
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              awaitingClarificationDetail
                ? "Type a little more detail for clarification..."  // When backend asks for more detail
                : "Type your message..."  // Default placeholder
            }
            disabled={isLoading}
            className="h-8 text-xs"
          />

          {/* Send button: disabled if loading or input is empty */}
          <Button
            type="submit"
            size="icon"
            disabled={isLoading || !input.trim()}
            className="h-8 w-8 shrink-0"
          >
            <Send className="h-3 w-3" />
          </Button>
        </form>
      )}
    </div>
  );
}
