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
  // Widget visibility state: whether the chat panel is open and whether it's minimized
  const { isOpen, isMinimized, setIsOpen, setIsMinimized } = useWidgetState();
  
  // Backend health status: "ok", "error", or "checking" - displayed as a status indicator
  const health = useHealthCheck();
  
  // Ref to the main widget panel - used for click-outside detection to close the widget
  const panelRef = useRef<HTMLDivElement>(null);

  // Flag to show/hide the confirmation prompt when user clicks "Return to main menu"
  const [isResetPromptVisible, setIsResetPromptVisible] = useState(false);
  
  // Loading flag while the reset API call is in progress
  const [isResettingHome, setIsResettingHome] = useState(false);
  
  // Version number used as a key for ChatWidgetContent to force re-mount after reset.
  // This ensures all state inside ChatWidgetContent is cleared when user returns to main menu.
  const [contentVersion, setContentVersion] = useState(0);

  // Get all booking/chat flow state to check if user has progress that would be lost
  // if they return to the main menu
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
    reset,  // Function to clear all booking state
  } = useBookingFlow();

  // Handle escape key and click-outside behavior to close the widget.
  // Escape closes the reset prompt first (if visible), then closes the widget.
  // Click outside the widget also closes it.
  useEffect(() => {
    // Escape key handler: close reset prompt if visible, otherwise close widget
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        if (isResetPromptVisible) {
          // Close the reset confirmation prompt
          setIsResetPromptVisible(false);
          return;
        }
        // Close the widget panel
        setIsOpen(false);
      }
    };

    // Click-outside handler: close widget if user clicks anywhere outside the panel
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    // Only attach listeners when widget is open
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        // Clean up listeners when widget closes or component unmounts
        document.removeEventListener("keydown", handleEscape);
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [isOpen, isResetPromptVisible, setIsOpen]);

  // Check if user has any progress in the current flow.
  // If true, show a confirmation prompt before allowing them to return to main menu.
  // This prevents accidentally losing their booking progress.
  const hasProgressToLose =
    currentMode !== null ||          // User selected a mode (complaint, direct, renewal)
    messages.length > 0 ||            // Chat history exists
    step !== "chat" ||                // User is past the initial chat step (e.g., in OTP, identity, etc.)
    selectedSpecialtyId !== null ||   // User selected a specialty
    selectedDoctorId !== null ||      // User selected a doctor
    selectedSlotId !== null ||        // User selected a time slot
    renewalItemId !== null ||         // User selected a medication to renew
    patientNationalId !== null ||     // Patient identity info collected
    patientEmail !== null ||          // Patient email collected
    otpVerified;                      // OTP verification completed

  // Apply the home reset locally without calling the backend API.
  // This clears all local booking state and forces ChatWidgetContent to remount.
  const applyLocalHomeReset = () => {
    // Clear the session correlation ID (used for tracking API calls)
    clearCorrelationId();
    // Reset all booking flow state (messages, selections, etc.)
    reset();
    // Increment version to force ChatWidgetContent to remount with clean state
    setContentVersion((value) => value + 1);
  };

  // Handler for "Return to main menu" button click.
  // If no progress, reset immediately. If progress exists, show confirmation prompt.
  const handleHomeClick = () => {
    // Don't allow reset while API calls are in progress
    if (flowLoading || isResettingHome) {
      return;
    }

    // If user has no progress, reset immediately without asking
    if (!hasProgressToLose) {
      applyLocalHomeReset();
      return;
    }

    // If user has progress, show confirmation prompt before resetting
    setIsResetPromptVisible(true);
  };

  // Handler for "Stay here" button in the reset confirmation prompt.
  // Just closes the prompt and continues the current flow.
  const handleStayHere = () => {
    // Don't close if reset is already in progress
    if (isResettingHome) {
      return;
    }
    // Hide the reset confirmation prompt
    setIsResetPromptVisible(false);
  };

  // Handler for "Return to main menu" confirmation button.
  // Calls backend to reset server-side state, then clears local state.
  const handleConfirmHomeReset = async () => {
    // Show loading state while API call is in progress
    setIsResettingHome(true);

    try {
      // Call backend to reset server-side booking/chat state (sessions, etc.)
      await chatReset();
      // Clear all local state and remount ChatWidgetContent
      applyLocalHomeReset();
      // Hide the reset confirmation prompt
      setIsResetPromptVisible(false);
      // Show success message to user
      toast.success("Returned to the main menu.");
    } catch (err: any) {
      // If reset fails, show error message
      toast.error(
        err.message || "Unable to return to the main menu right now.",
      );
    } finally {
      // Always clear loading state whether request succeeded or failed
      setIsResettingHome(false);
    }
  };

  return (
    <>
      {/* Mobile-only backdrop overlay: closes widget when tapped on mobile/tablet */}
      {isOpen && !isMinimized && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Main chat widget panel container.
          When closed/minimized: hidden (opacity-0, scale-0)
          When open: expanded to fill screen on mobile or fixed size on desktop */}
      <div
        ref={panelRef}
        className={cn(
          "fixed bottom-4 right-4 z-50 flex flex-col bg-card rounded-xl border shadow-lg transition-all duration-300",
          isOpen && !isMinimized
            ? "w-full h-[85vh] sm:w-[380px] sm:h-[560px] opacity-100 scale-100"  // Open state
            : "w-14 h-14 opacity-0 scale-0 pointer-events-none",  // Closed state
        )}
      >
        {/* Widget content: only shown when open and not minimized */}
        {isOpen && !isMinimized && (
          <>
            {/* Header bar: contains title, health status, and action buttons */}
            <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
              {/* Left side: home button and title */}
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

              {/* Right side: status indicator and action buttons */}
              <div className="flex items-center gap-1 shrink-0 ml-2">
                {/* Health status indicator dot: green (ok), red (error), or pulsing gray (checking) */}
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <div
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      health === "ok" && "bg-[hsl(var(--success))]",  // Green: API healthy
                      health === "error" && "bg-destructive",           // Red: API down
                      health === "checking" &&
                        "bg-muted-foreground animate-pulse",            // Gray pulsing: checking status
                    )}
                  />
                </div>

                {/* Minimize button: collapse widget to just the floating button */}
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={() => setIsMinimized(true)}
                  disabled={isResettingHome}
                >
                  <Minus className="h-3 w-3" />
                </Button>

                {/* Close button: hide widget entirely */}
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

            {/* Reset confirmation prompt: shown when user clicks home button with progress */}
            {isResetPromptVisible && (
              <div className="border-b bg-muted/25 px-3 py-3 shrink-0">
                <div className="rounded-lg border bg-background p-3 shadow-sm">
                  <div className="flex items-start gap-3">
                    {/* Warning icon */}
                    <div className="mt-0.5 rounded-full bg-amber-100 p-2 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                      <TriangleAlert className="h-4 w-4" />
                    </div>

                    {/* Prompt content */}
                    <div className="flex-1 min-w-0">
                      {/* Title with home icon */}
                      <div className="flex items-center gap-2">
                        <House className="h-4 w-4 text-muted-foreground" />
                        <p className="text-sm font-semibold">
                          Return to the main menu?
                        </p>
                      </div>

                      {/* Warning message explaining what will happen */}
                      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                        This will cancel the current booking or renewal flow and
                        take you back to the main menu.
                      </p>

                      {/* Action buttons: Stay or Confirm */}
                      <div className="mt-3 flex flex-wrap gap-2">
                        {/* Cancel reset button */}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleStayHere}
                          disabled={isResettingHome}
                        >
                          Stay here
                        </Button>

                        {/* Confirm reset button with loading spinner */}
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

            {/* Chat content area: renders the booking flow interface.
                Faded out (opacity-60) when reset prompt is visible to show it's disabled. */}
            <div
              className={cn(
                "flex-1 min-h-0 overflow-hidden transition-opacity",
                isResetPromptVisible && "opacity-60 pointer-events-none",  // Faded when prompt visible
              )}
            >
              {/* Key prop forces component remount when contentVersion changes (after reset) */}
              <ChatWidgetContent key={contentVersion} />
            </div>
          </>
        )}
      </div>

      {/* Floating button: shown when widget is closed or minimized.
          Clicking opens the widget back up. */}
      {(!isOpen || isMinimized) && (
        <button
          onClick={() => {
            // Open the widget and un-minimize it
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