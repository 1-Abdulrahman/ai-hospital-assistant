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

export default function ChatWidgetContent() {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [awaitingClarificationDetail, setAwaitingClarificationDetail] = useState(false);

  const {
    step,
    messages,
    currentMode,
    isLoading,
    selectedSpecialtyId,
    selectedDoctorId,
    selectedSlotId,
    renewalItemId,
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
    setSelectedSpecialtyLabel,
    setSelectedDoctorLabel,
    setSelectedSlotLabel,
    setSelectedSlotStartUtc,
    setRenewalItemLabel,
  } = useBookingFlow();

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const handleResponseErrors = (res: ChatResponse) => {
    if (res.errors?.length) {
      toast.error(res.errors[0].userMessage);
      console.debug("[API reasonCode]", res.errors[0].reasonCode);
    }
  };

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
      setAwaitingClarificationDetail(Boolean(res.needsClarification));
    } catch (err: any) {
      addMessage({
        role: "assistant",
        text: err.message || "An error occurred.",
      });
    } finally {
      setLoading(false);
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
      const res =
        mode === "direct"
          ? await chatDirectStart()
          : await chatRenewalRequest();

      addMessage(responseToMessage(res));
      handleResponseErrors(res);

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

  const handleSelection = async (listType: string, item: SelectionListItem) => {
    const actionMap: Record<string, string> = {
      specialty: "SELECT_SPECIALTY",
      doctor: "SELECT_DOCTOR",
      slot: "SELECT_SLOT",
      date: "SELECT_DATE",
      medication: "SELECT_MEDICATION_FOR_RENEWAL",
    };

    if (listType === "specialty") {
      setSelectedSpecialtyId(item.id);
      setSelectedSpecialtyLabel(item.label);
    }

    if (listType === "doctor") {
      setSelectedDoctorId(item.id);
      setSelectedDoctorLabel(item.label);
    }

    if (listType === "slot") {
      setSelectedSlotId(item.id);
      setSelectedSlotLabel(item.label);
      setSelectedDoctorLabel(
        item.meta?.practitionerDisplay ??
          item.label.split("•")[0]?.trim() ??
          null,
      );
      setSelectedSlotStartUtc(item.meta?.isoDate ?? null);

      if (item.meta?.dateKey) {
        setSelectedDate(item.meta.dateKey);
      } else if (item.meta?.isoDate) {
        setSelectedDate(item.meta.isoDate);
      }
    }

    if (listType === "medication") {
      setRenewalItemId(item.id);
      setRenewalItemLabel(item.label);
    }
    setLoading(true);

    try {
      const res = await chatSelection({
        selectionType: listType,
        selectionId: item.id,
        selectionValue: item.label,
        action: actionMap[listType] || listType.toUpperCase(),
      });

      addMessage(responseToMessage(res));
      handleResponseErrors(res);

      if (res.requiresContinuityIdentity) {
        setStep("continuity_identity");
        return;
      }

      const hasBackendErrors = Boolean(res.errors?.length);

      if (
        currentMode === "renewal" &&
        listType === "medication" &&
        !hasBackendErrors
      ) {
        setStep("otp");
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

  const handleQuickReply = async (qr: QuickReply) => {
    if (qr.action === "PROMPT_FOR_TEXT") {
      addMessage({ role: "user", text: qr.label });
      addMessage({
        role: "assistant",
        text: "Please type a little more detail. I will combine it with your earlier complaint before checking the specialty again.",
      });
      setAwaitingClarificationDetail(true);
      inputRef.current?.focus();
      return;
    }

    addMessage({ role: "user", text: qr.value });
    setLoading(true);

    try {
      const res = await sendChatMessage(qr.value);
      addMessage(responseToMessage(res));
      handleResponseErrors(res);
      setAwaitingClarificationDetail(Boolean(res.needsClarification));
    } catch (err: any) {
      addMessage({
        role: "assistant",
        text: err.message || "An error occurred.",
      });
    } finally {
      setLoading(false);
    }
  };

  if (step === "renewal_identity") return <ChatWidgetRenewalIdentity />;
  if (step === "continuity_identity") return <ChatWidgetContinuityIdentity />;
  if (step === "otp") return <ChatWidgetOtp />;
  if (step === "confirm") return <ChatWidgetConfirm />;

  const firstConsentIndex = messages.findIndex((msg) => msg.showConsentNotice);

  return (
    <div className="flex flex-col h-full">
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-3"
      >
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
              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs gap-2"
                onClick={() => handleModeStart("complaint")}
              >
                <Stethoscope className="h-3.5 w-3.5" />
                Describe Symptoms
              </Button>

              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs gap-2"
                onClick={() => handleModeStart("direct")}
              >
                <Calendar className="h-3.5 w-3.5" />
                Schedule Directly
              </Button>

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

        {messages.map((msg, idx) => (
          <div
            key={msg.id}
            className={cn(
              "flex flex-col",
              msg.role === "user" ? "items-end" : "items-start"
            )}
          >
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

            {msg.role === "assistant" && (
              <>
                {msg.showConsentNotice && idx === firstConsentIndex && (
                  <ConsentBanner />
                )}

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

                {msg.confirmationSummary && (
                  <ConfirmationCard
                    confirmationType={msg.confirmationType}
                    confirmationSummary={msg.confirmationSummary}
                    messageText={msg.text}
                  />
                )}

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

                {msg.quickReplies && msg.quickReplies.length > 0 && (
                  <div className="mt-2 flex flex-col gap-1 max-w-[85%]">
                    {msg.needsClarification && (
                      <p className="text-[11px] text-muted-foreground">
                        Tap below to add more detail, or choose one of the suggested specialties.
                      </p>
                    )}

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

        {isLoading && (
          <div className="flex justify-start">
            <Card className="bg-muted px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </Card>
          </div>
        )}

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
            placeholder={
              awaitingClarificationDetail
                ? "Type a little more detail for clarification..."
                : "Type your message..."
            }
            disabled={isLoading}
            className="h-8 text-xs"
          />

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
