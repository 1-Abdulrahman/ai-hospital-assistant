// React hooks for state management
import { useState } from "react";

// Icons from lucide-react
import { Loader2, Mail, ChevronLeft } from "lucide-react";

// UI components from shadcn/ui library
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
// OTP input component: displays 6 input slots for one-time password
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";

// Hook to access booking flow state and actions
import { useBookingFlow } from "@/hooks/use-booking-flow";

// API client functions for OTP flow
import { requestOtp, verifyOtp, chatConfirm } from "@/lib/api-client";

// Toast notification library for displaying success/error messages
import { toast } from "sonner";

// Validate email address format using a simple regex pattern.
// Checks for: non-whitespace chars @ non-whitespace chars . non-whitespace chars
// Examples: valid@example.com ✓, invalid.email ✗, @example.com ✗
function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

// OTP verification step: handles identity verification before booking/renewal.
// User provides national ID and email, receives OTP via email, then enters it to verify.
// For renewal mode: auto-confirms after successful OTP verification.
// For appointment mode: proceeds to final confirmation screen.
export default function ChatWidgetOtp() {
  // Local state: OTP code entered by user
  const [otp, setOtp] = useState("");
  
  // Track if OTP has been requested (switches UI from request to input mode)
  const [otpRequested, setOtpRequested] = useState(false);
  
  // Track if API calls are in progress (disables inputs and buttons)
  const [loading, setLoading] = useState(false);

  // Extract booking flow state and actions
  const {
    // Current flow mode: "complaint", "direct", or "renewal"
    currentMode,
    // Medication ID for renewal flow
    renewalItemId,
    // Patient identity information
    patientNationalId,
    patientEmail,
    // Actions to update patient info
    setPatientNationalId,
    setPatientEmail,
    // Mark OTP as verified
    setOtpVerified,
    // Navigate to next step
    setStep,
    // Add message to chat history
    addMessage,
  } = useBookingFlow();

  // Current values from state (with fallbacks to empty string)
  const nationalId = patientNationalId || "";
  const email = patientEmail || "";

  // Validate email format
  const emailValid = isValidEmail(email);
  
  // Can request OTP only if both national ID and valid email are provided
  const canRequestOtp = nationalId.trim().length > 0 && emailValid;

  // Handler for "Request OTP" button.
  // Validates user input, sends OTP request to backend (email gets OTP code),
  // and switches UI from input form to OTP entry screen.
  const handleRequestOtp = async () => {
    // Validation: check national ID
    if (!nationalId.trim()) {
      toast.error("Enter national ID before requesting OTP.");
      return;
    }

    // Validation: check email exists
    if (!email.trim()) {
      toast.error("Enter email before requesting OTP.");
      return;
    }

    // Validation: check email format
    if (!emailValid) {
      toast.error("Please enter a valid email address before requesting OTP.");
      return;
    }

    // Show loading state
    setLoading(true);
    try {
      // Call backend to send OTP email
      const response = await requestOtp(nationalId.trim(), email.trim());
      // Switch UI to OTP input mode (show 6-digit input and verify button)
      setOtpRequested(true);
      // Show success message to user
      toast.success(response.message || "OTP sent successfully.");
    } catch (err: any) {
      // Show error if OTP request failed
      toast.error(err.message || "Failed to request OTP.");
    } finally {
      // Always clear loading state
      setLoading(false);
    }
  };

  // Handler for "Verify OTP" button.
  // Validates all fields, sends OTP to backend for verification,
  // then proceeds to next step based on booking mode.
  const handleVerify = async () => {
    // Validation: check all required fields are still present
    
    if (!nationalId.trim()) {
      toast.error("National ID is missing.");
      return;
    }

    if (!email.trim()) {
      toast.error("Email is missing.");
      return;
    }

    if (!emailValid) {
      toast.error("Please enter a valid email address before verifying OTP.");
      return;
    }

    // Validation: ensure 6-digit OTP was entered
    if (otp.length < 6) {
      toast.error("Enter the 6-digit OTP.");
      return;
    }

    // Show loading state
    setLoading(true);
    try {
      // Send OTP to backend for verification
      const res = await verifyOtp({
        nationalId: nationalId.trim(),
        email: email.trim(),
        otp,
      });

      // Check if verification was successful
      if (res.verified) {
        // Mark OTP as verified in booking flow
        setOtpVerified(true);

        // For renewal mode: auto-confirm after OTP verification
        // (renewal doesn't need final confirmation step)
        if (currentMode === "renewal") {
          // Call confirm endpoint to finalize renewal
          const confirmRes = await chatConfirm({
            action: "CONFIRM_RENEWAL",
            renewalItemId: renewalItemId || undefined,
            nationalId: nationalId.trim(),
            email: email.trim(),
          });

          // Add confirmation response to chat history
          addMessage({
            role: "assistant",
            text: confirmRes.userMessage,
            confirmationType: confirmRes.confirmationType,
            confirmationSummary: confirmRes.confirmationSummary,
            bookingReferenceId: confirmRes.bookingReferenceId,
          });

          // Move to final "done" step (show success screen)
          setStep("done");
        } else {
          // For appointment mode: proceed to final confirmation screen
          // where user reviews all details before confirming
          setStep("confirm");
        }
      } else {
        // OTP verification failed: show error message from backend
        toast.error(res.message || "Invalid OTP. Please try again.");
      }
    } catch (err: any) {
      // Network or parsing error
      toast.error(err.message || "Failed to verify OTP.");
    } finally {
      // Always clear loading state
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      {/* Header: step title */}
      <h3 className="font-semibold text-sm mb-3">Verify Your Identity</h3>

      {/* Input fields for national ID and email (shown before OTP is requested) */}
      <div className="space-y-3 mb-4">
        {/* National ID input: accepts any ID format (passport, ID card, Iqama, Border ID, etc.) */}
        <Input
          value={nationalId}
          onChange={(e) => setPatientNationalId(e.target.value)}
          placeholder="National ID / Iqama / Border ID"
          className="h-8 text-xs"
          // Disable once OTP is requested (user shouldn't change ID mid-process)
          disabled={loading || otpRequested}
        />

        {/* Email input: where OTP will be sent to */}
        <Input
          value={email}
          onChange={(e) => setPatientEmail(e.target.value)}
          placeholder="Email address"
          type="email"
          className="h-8 text-xs"
          // Disable once OTP is requested
          disabled={loading || otpRequested}
        />

        {/* Email validation error: shown when email is invalid */}
        {!!email.trim() && !emailValid && (
          <p className="text-[11px] text-destructive">
            Please enter a valid email address.
          </p>
        )}
      </div>

      {/* Helper box: instructions for testing with MailHog (local email testing tool) */}
      <div className="rounded-lg border border-border bg-accent/50 px-3 py-2 text-xs mb-4">
        <div className="flex items-start gap-2">
          {/* Mail icon */}
          <Mail className="mt-0.5 h-3 w-3 text-primary shrink-0" />
          <div className="text-[11px]">
            <p className="font-medium">Open MailHog at</p>
            {/* Link to local MailHog instance for viewing test emails */}
            <a
              href="http://localhost:8025"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-1"
            >
              localhost:8025
            </a>
          </div>
        </div>
      </div>

      {/* Conditional rendering: show "Request OTP" button OR OTP input form */}
      {!otpRequested ? (
        // Before OTP requested: show "Request OTP" button
        <Button
          size="sm"
          onClick={handleRequestOtp}
          disabled={loading || !canRequestOtp}  // Disable if loading or validation fails
          className="w-full h-8 text-xs"
        >
          {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
          Request OTP
        </Button>
      ) : (
        // After OTP requested: show OTP input and verify button
        <div className="space-y-3">
          {/* OTP input: 6-digit input slots */}
          <div className="flex justify-center mb-2">
            <InputOTP maxLength={6} value={otp} onChange={setOtp}>
              <InputOTPGroup>
                <InputOTPSlot index={0} />
                <InputOTPSlot index={1} />
                <InputOTPSlot index={2} />
                <InputOTPSlot index={3} />
                <InputOTPSlot index={4} />
                <InputOTPSlot index={5} />
              </InputOTPGroup>
            </InputOTP>
          </div>

          {/* Verify button: submits 6-digit OTP to backend */}
          <Button
            size="sm"
            className="w-full h-8 text-xs"
            onClick={handleVerify}
            disabled={loading || otp.length < 6 || !emailValid}  // Disabled if OTP incomplete
          >
            {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            Verify OTP
          </Button>

          {/* Resend button: requests a new OTP code if user didn't receive the first one */}
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs h-7"
            onClick={handleRequestOtp}
            disabled={loading}
          >
            Resend OTP
          </Button>
        </div>
      )}

      {/* Back button: returns to chat to restart the flow or go back */}
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
