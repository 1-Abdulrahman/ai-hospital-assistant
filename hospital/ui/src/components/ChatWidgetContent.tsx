import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Calendar, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { sendChatMessage } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import ChatWidgetClarify from "./steps/ChatWidgetClarify";
import ChatWidgetBook from "./steps/ChatWidgetBook";
import ChatWidgetOtp from "./steps/ChatWidgetOtp";
import ChatWidgetConfirm from "./steps/ChatWidgetConfirm";

export default function ChatWidgetContent() {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const { step, messages, candidates, addMessage, setStep, setCandidates, isLoading, setLoading, setError } = useBookingFlow();

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
      addMessage({
        role: "assistant",
        text: res.userMessage,
        candidates: res.candidates,
        ambiguous: res.ambiguous,
        quickReplies: res.quickReplies,
        selectionLists: res.selectionLists,
        needsClarification: res.needsClarification,
        isChronicContinuity: res.isChronicContinuity,
        showConsentNotice: res.showConsentNotice,
      });
      if (res.needsClarification && res.candidates?.length) {
        setCandidates(res.candidates);
        setStep("clarify");
      }
    } catch (err: any) {
      addMessage({ role: "assistant", text: err.message || "An error occurred." });
    } finally {
      setLoading(false);
    }
  };

  const handleQuickReply = (value: string) => {
    setInput(value);
  };

  if (step === "clarify") {
    return <ChatWidgetClarify candidates={candidates} />;
  }

  if (step === "book") {
    return <ChatWidgetBook />;
  }

  if (step === "otp") {
    return <ChatWidgetOtp />;
  }

  if (step === "confirm") {
    return <ChatWidgetConfirm />;
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center pt-8 text-center">
            <div className="mb-3 rounded-full bg-accent p-3">
              <Calendar className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-base font-semibold">Book an Appointment</h2>
            <p className="mt-1 text-xs text-muted-foreground px-2">
              Describe your symptoms or schedule directly.
            </p>
            <Button size="sm" className="mt-3" onClick={() => setStep("book")}>
              Schedule Directly
            </Button>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
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
              {msg.candidates && msg.candidates.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {msg.candidates.map((c) => (
                    <Badge key={c.label} variant="secondary" className="text-[10px]">
                      {c.label} — {Math.round(c.p * 100)}%
                    </Badge>
                  ))}
                </div>
              )}
              {msg.quickReplies && msg.quickReplies.length > 0 && (
                <div className="mt-2 flex flex-col gap-1">
                  {msg.quickReplies.map((qr) => (
                    <Button
                      key={qr.value}
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      onClick={() => handleQuickReply(qr.value)}
                    >
                      {qr.label}
                    </Button>
                  ))}
                </div>
              )}
              {msg.isChronicContinuity && (
                <div className="mt-2 rounded bg-accent/50 px-2 py-1.5 text-[10px] text-accent-foreground">
                  ⚕️ Previous physician prioritized
                </div>
              )}
            </Card>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <Card className="bg-muted px-3 py-2">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </Card>
          </div>
        )}
      </div>
      <form
        className="flex gap-2 border-t px-4 py-2 shrink-0"
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
      >
        <Input
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
    </div>
  );
}
