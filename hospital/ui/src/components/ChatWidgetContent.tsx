import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Calendar, Pill, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { sendChatMessage, chatDirectStart, chatRenewalRequest, chatSelection } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { ChatResponse, SelectionListItem } from "@/lib/types";
import SelectionList from "./chat/SelectionList";
import ConsentBanner from "./chat/ConsentBanner";
import ContinuityBanner from "./chat/ContinuityBanner";
import ConfirmationCard from "./chat/ConfirmationCard";
import ChatWidgetOtp from "./steps/ChatWidgetOtp";
import ChatWidgetConfirm from "./steps/ChatWidgetConfirm";

/** Helper to map a ChatResponse to an assistant message payload */
function responseToMessage(res: ChatResponse) {
  return {
    role: "assistant" as const,
    text: res.userMessage,
    quickReplies: res.quickReplies,
    selectionLists: res.selectionLists,
    needsClarification: res.needsClarification,
    isChronicContinuity: res.isChronicContinuity,
    showConsentNotice: res.showConsentNotice,
    bookingReferenceId: res.bookingReferenceId,
    confirmationType: res.confirmationType,
    confirmationSummary: res.confirmationSummary,
  };
}

export default function ChatWidgetContent() {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    step, messages, currentMode, isLoading,
    selectedSpecialtyId, selectedDoctorId, selectedSlotId,
    addMessage, setStep, setCurrentMode, setLoading, setError,
    setSelectedSpecialtyId, setSelectedDoctorId, setSelectedSlotId, setSelectedDate,
    setRenewalItemId, resetFlow,
  } = useBookingFlow();

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    addMessage({ role: "user", text });
    setLoading(true);
    setError(null);
    try {
      const res = await sendChatMessage(text);
      addMessage(responseToMessage(res));
      handleResponseErrors(res);
    } catch (err: any) {
      addMessage({ role: "assistant", text: err.message || "An error occurred." });
    } finally {
      setLoading(false);
    }
  };

  const handleResponseErrors = (res: ChatResponse) => {
    if (res.errors?.length) {
      toast.error(res.errors[0].userMessage);
      console.debug("[API reasonCode]", res.errors[0].reasonCode);
    }
  };

  const handleModeStart = async (mode: "complaint" | "direct" | "renewal") => {
    setCurrentMode(mode);
    if (mode === "complaint") {
      inputRef.current?.focus();
      return;
    }
    setLoading(true);
    try {
      const res = mode === "direct" ? await chatDirectStart() : await chatRenewalRequest();
      addMessage(responseToMessage(res));
      handleResponseErrors(res);
    } catch (err: any) {
      addMessage({ role: "assistant", text: err.message || "An error occurred." });
    } finally {
      setLoading(false);
    }
  };

  const handleSelection = async (listType: string, item: SelectionListItem) => {
    const actionMap: Record<string, string> = {
      specialty: "SELECT_SPECIALTY",
      doctor: "SELECT_DOCTOR",
      slot: "SELECT_SLOT",
      date: "SELECT_DATE",
      medication: "SELECT_MEDICATION_FOR_RENEWAL",
    };

    // For slot: store locally, show CTA for verification
    if (listType === "slot") {
      setSelectedSlotId(item.id);
      // Only set selectedDate if backend provides isoDate — no inference
      if (item.meta?.isoDate) {
        setSelectedDate(item.meta.isoDate);
      }
      return;
    }

    // Store selection in state
    if (listType === "specialty") setSelectedSpecialtyId(item.id);
    if (listType === "doctor") setSelectedDoctorId(item.id);
    if (listType === "medication") setRenewalItemId(item.id);

    // Send structured selection to backend
    setLoading(true);
    try {
      const res = await chatSelection({
        selectionType: listType,
        selectionId: item.id,
        action: actionMap[listType] || listType.toUpperCase(),
      });
      addMessage(responseToMessage(res));
      handleResponseErrors(res);
    } catch (err: any) {
      addMessage({ role: "assistant", text: err.message || "An error occurred." });
    } finally {
      setLoading(false);
    }
  };

  const handleQuickReply = async (value: string) => {
    addMessage({ role: "user", text: value });
    setLoading(true);
    try {
      const res = await sendChatMessage(value);
      addMessage(responseToMessage(res));
      handleResponseErrors(res);
    } catch (err: any) {
      addMessage({ role: "assistant", text: err.message || "An error occurred." });
    } finally {
      setLoading(false);
    }
  };

  // Step overlays — only OTP and confirm render as overlays
  if (step === "otp") return <ChatWidgetOtp />;
  if (step === "confirm") return <ChatWidgetConfirm />;

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {/* Welcome screen: no messages and no mode selected */}
        {messages.length === 0 && !currentMode && (
          <div className="flex flex-col items-center justify-center pt-8 text-center">
            <div className="mb-3 rounded-full bg-accent p-3">
              <Calendar className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-base font-semibold">How can we help?</h2>
            <p className="mt-1 text-xs text-muted-foreground px-2">
              Choose an option to get started.
            </p>
            <div className="mt-4 flex flex-col gap-2 w-full max-w-[220px]">
              <Button size="sm" variant="outline" className="w-full text-xs gap-2" onClick={() => handleModeStart("complaint")}>
                <Stethoscope className="h-3.5 w-3.5" /> Describe Symptoms
              </Button>
              <Button size="sm" variant="outline" className="w-full text-xs gap-2" onClick={() => handleModeStart("direct")}>
                <Calendar className="h-3.5 w-3.5" /> Schedule Directly
              </Button>
              <Button size="sm" variant="outline" className="w-full text-xs gap-2" onClick={() => handleModeStart("renewal")}>
                <Pill className="h-3.5 w-3.5" /> Medication Renewal
              </Button>
            </div>
          </div>
        )}

        {/* Message thread */}
        {messages.map((msg) => (
          <div key={msg.id} className={cn("flex flex-col", msg.role === "user" ? "items-end" : "items-start")}>
            <Card
              className={cn(
                "max-w-[85%] px-3 py-2 text-xs",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted"
              )}
            >
              <p className="whitespace-pre-wrap">{msg.text}</p>
            </Card>

            {/* UI only reacts to explicit backend flags — no inference from empty lists */}
            {msg.role === "assistant" && (
              <>
                {msg.showConsentNotice && <ConsentBanner />}
                {msg.isChronicContinuity && <ContinuityBanner />}

                {msg.confirmationSummary && (
                  <ConfirmationCard
                    confirmationType={msg.confirmationType}
                    confirmationSummary={msg.confirmationSummary}
                    messageText={msg.text}
                  />
                )}

                {msg.selectionLists?.map((list, idx) => (
                  <SelectionList
                    key={`${list.type}-${idx}`}
                    list={list}
                    onSelect={(item) => handleSelection(list.type, item)}
                    selectedId={
                      list.type === "specialty" ? selectedSpecialtyId :
                      list.type === "doctor" ? selectedDoctorId :
                      list.type === "slot" ? selectedSlotId :
                      null
                    }
                    disabled={isLoading}
                  />
                ))}

                {/* After slot selection, show CTA to continue to OTP verification */}
                {msg.selectionLists?.some(l => l.type === "slot") && selectedSlotId && (
                  <Button
                    size="sm"
                    className="mt-2 w-full h-8 text-xs"
                    onClick={() => setStep("otp")}
                  >
                    Continue to Verification
                  </Button>
                )}

                {msg.quickReplies && msg.quickReplies.length > 0 && (
                  <div className="mt-2 flex flex-col gap-1 max-w-[85%]">
                    {msg.quickReplies.map((qr) => (
                      <Button
                        key={qr.value}
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => handleQuickReply(qr.value)}
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

        {isLoading && (
          <div className="flex justify-start">
            <Card className="bg-muted px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </Card>
          </div>
        )}

        {/* Done state: allow starting a new booking */}
        {step === "done" && (
          <div className="flex justify-center pt-2">
            <Button size="sm" variant="outline" className="text-xs" onClick={resetFlow}>
              Start New Booking
            </Button>
          </div>
        )}
      </div>

      {/* Input area — hidden when done */}
      {step !== "done" && (
        <form
          className="flex gap-2 border-t px-4 py-2 shrink-0"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe symptoms…"
            disabled={isLoading}
            className="h-8 text-xs"
          />
          <Button type="submit" size="icon" disabled={isLoading || !input.trim()} className="h-8 w-8 shrink-0">
            <Send className="h-3 w-3" />
          </Button>
        </form>
      )}
    </div>
  );
}
