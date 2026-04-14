import { useState, useEffect, useRef } from "react";
import {
  X,
  Minus,
  MessageCircle,
  Activity,
  Loader2,
  House,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWidgetState } from "@/hooks/use-widget-state";
import { useHealthCheck } from "@/hooks/use-health-check";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { chatReset } from "@/lib/api-client";
import { clearCorrelationId } from "@/lib/session";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import ChatWidgetContent from "./ChatWidgetContent";

export default function ChatWidget() {
  const { isOpen, isMinimized, setIsOpen, setIsMinimized } = useWidgetState();
  const health = useHealthCheck();
  const panelRef = useRef<HTMLDivElement>(null);

  const [isResetPromptVisible, setIsResetPromptVisible] = useState(false);
  const [isResettingHome, setIsResettingHome] = useState(false);
  const [contentVersion, setContentVersion] = useState(0);

  const {
    step,
    messages,
    currentMode,
    isLoading: flowLoading,
    selectedSpecialtyId,
    selectedDoctorId,
    selectedSlotId,
    renewalItemId,
    patientNationalId,
    patientEmail,
    otpVerified,
    reset,
  } = useBookingFlow();

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        if (isResetPromptVisible) {
          setIsResetPromptVisible(false);
          return;
        }
        setIsOpen(false);
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("keydown", handleEscape);
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [isOpen, isResetPromptVisible, setIsOpen]);

  const hasProgressToLose =
    currentMode !== null ||
    messages.length > 0 ||
    step !== "chat" ||
    selectedSpecialtyId !== null ||
    selectedDoctorId !== null ||
    selectedSlotId !== null ||
    renewalItemId !== null ||
    patientNationalId !== null ||
    patientEmail !== null ||
    otpVerified;

  const applyLocalHomeReset = () => {
    clearCorrelationId();
    reset();
    setContentVersion((value) => value + 1);
  };

  const handleHomeClick = () => {
    if (flowLoading || isResettingHome) {
      return;
    }

    if (!hasProgressToLose) {
      applyLocalHomeReset();
      return;
    }

    setIsResetPromptVisible(true);
  };

  const handleStayHere = () => {
    if (isResettingHome) {
      return;
    }
    setIsResetPromptVisible(false);
  };

  const handleConfirmHomeReset = async () => {
    setIsResettingHome(true);

    try {
      await chatReset();
      applyLocalHomeReset();
      setIsResetPromptVisible(false);
      toast.success("Returned to the main menu.");
    } catch (err: any) {
      toast.error(
        err.message || "Unable to return to the main menu right now.",
      );
    } finally {
      setIsResettingHome(false);
    }
  };

  return (
    <>
      {isOpen && !isMinimized && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      <div
        ref={panelRef}
        className={cn(
          "fixed bottom-4 right-4 z-50 flex flex-col bg-card rounded-xl border shadow-lg transition-all duration-300",
          isOpen && !isMinimized
            ? "w-full h-[85vh] sm:w-[380px] sm:h-[560px] opacity-100 scale-100"
            : "w-14 h-14 opacity-0 scale-0 pointer-events-none",
        )}
      >
        {isOpen && !isMinimized && (
          <>
            <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
              <button
                type="button"
                onClick={handleHomeClick}
                disabled={flowLoading || isResettingHome}
                aria-label="Return to the main menu"
                className="flex items-center gap-2 min-w-0 text-left transition-colors hover:text-primary disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Activity className="h-4 w-4 text-primary shrink-0" />
                <span className="font-semibold text-sm truncate hover:underline">
                  Hospital Booking
                </span>
              </button>

              <div className="flex items-center gap-1 shrink-0 ml-2">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <div
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      health === "ok" && "bg-[hsl(var(--success))]",
                      health === "error" && "bg-destructive",
                      health === "checking" &&
                        "bg-muted-foreground animate-pulse",
                    )}
                  />
                </div>

                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={() => setIsMinimized(true)}
                  disabled={isResettingHome}
                >
                  <Minus className="h-3 w-3" />
                </Button>

                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={() => setIsOpen(false)}
                  disabled={isResettingHome}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>

            {isResetPromptVisible && (
              <div className="border-b bg-muted/25 px-3 py-3 shrink-0">
                <div className="rounded-lg border bg-background p-3 shadow-sm">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-full bg-amber-100 p-2 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                      <TriangleAlert className="h-4 w-4" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <House className="h-4 w-4 text-muted-foreground" />
                        <p className="text-sm font-semibold">
                          Return to the main menu?
                        </p>
                      </div>

                      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                        This will cancel the current booking or renewal flow and
                        take you back to the main menu.
                      </p>

                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleStayHere}
                          disabled={isResettingHome}
                        >
                          Stay here
                        </Button>

                        <Button
                          type="button"
                          size="sm"
                          onClick={() => void handleConfirmHomeReset()}
                          disabled={isResettingHome}
                        >
                          {isResettingHome && (
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          )}
                          Return to main menu
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div
              className={cn(
                "flex-1 min-h-0 overflow-hidden transition-opacity",
                isResetPromptVisible && "opacity-60 pointer-events-none",
              )}
            >
              <ChatWidgetContent key={contentVersion} />
            </div>
          </>
        )}
      </div>

      {(!isOpen || isMinimized) && (
        <button
          onClick={() => {
            setIsOpen(true);
            setIsMinimized(false);
          }}
          className="fixed bottom-4 right-4 z-50 flex items-center justify-center h-14 w-14 rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl hover:scale-110 transition-all duration-200"
          aria-label="Open chat"
        >
          <MessageCircle className="h-5 w-5" />
        </button>
      )}
    </>
  );
}