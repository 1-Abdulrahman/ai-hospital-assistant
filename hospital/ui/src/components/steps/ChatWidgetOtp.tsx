import { useState } from "react";
import { Loader2, Mail, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { requestOtp, verifyOtp, chatConfirm } from "@/lib/api-client";
import { toast } from "sonner";

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export default function ChatWidgetOtp() {
  const [otp, setOtp] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [loading, setLoading] = useState(false);

  const {
    currentMode,
    renewalItemId,
    patientNationalId,
    patientEmail,
    setPatientNationalId,
    setPatientEmail,
    setOtpVerified,
    setStep,
    addMessage,
  } = useBookingFlow();

  const nationalId = patientNationalId || "";
  const email = patientEmail || "";

  const emailValid = isValidEmail(email);
  const canRequestOtp = nationalId.trim().length > 0 && emailValid;

  const handleRequestOtp = async () => {
    if (!nationalId.trim()) {
      toast.error("Enter national ID before requesting OTP.");
      return;
    }

    if (!email.trim()) {
      toast.error("Enter email before requesting OTP.");
      return;
    }

    if (!emailValid) {
      toast.error("Please enter a valid email address before requesting OTP.");
      return;
    }

    setLoading(true);
    try {
      const response = await requestOtp(nationalId.trim(), email.trim());
      setOtpRequested(true);
      toast.success(response.message || "OTP sent successfully.");
    } catch (err: any) {
      toast.error(err.message || "Failed to request OTP.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
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

    if (otp.length < 6) {
      toast.error("Enter the 6-digit OTP.");
      return;
    }

    setLoading(true);
    try {
      const res = await verifyOtp({
        nationalId: nationalId.trim(),
        email: email.trim(),
        otp,
      });

      if (res.verified) {
        setOtpVerified(true);

        if (currentMode === "renewal") {
          const confirmRes = await chatConfirm({
            action: "CONFIRM_RENEWAL",
            renewalItemId: renewalItemId || undefined,
            nationalId: nationalId.trim(),
            email: email.trim(),
          });

          addMessage({
            role: "assistant",
            text: confirmRes.userMessage,
            confirmationType: confirmRes.confirmationType,
            confirmationSummary: confirmRes.confirmationSummary,
            bookingReferenceId: confirmRes.bookingReferenceId,
          });

          setStep("done");
        } else {
          setStep("confirm");
        }
      } else {
        toast.error(res.message || "Invalid OTP. Please try again.");
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to verify OTP.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      <h3 className="font-semibold text-sm mb-3">Verify Your Identity</h3>

      <div className="space-y-3 mb-4">
        <Input
          value={nationalId}
          onChange={(e) => setPatientNationalId(e.target.value)}
          placeholder="National ID / Iqama / Border ID"
          className="h-8 text-xs"
          disabled={loading || otpRequested}
        />

        <Input
          value={email}
          onChange={(e) => setPatientEmail(e.target.value)}
          placeholder="Email address"
          type="email"
          className="h-8 text-xs"
          disabled={loading || otpRequested}
        />

        {!!email.trim() && !emailValid && (
          <p className="text-[11px] text-destructive">
            Please enter a valid email address.
          </p>
        )}
      </div>

      <div className="rounded-lg border border-border bg-accent/50 px-3 py-2 text-xs mb-4">
        <div className="flex items-start gap-2">
          <Mail className="mt-0.5 h-3 w-3 text-primary shrink-0" />
          <div className="text-[11px]">
            <p className="font-medium">Open MailHog at</p>
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

      {!otpRequested ? (
        <Button
          size="sm"
          onClick={handleRequestOtp}
          disabled={loading || !canRequestOtp}
          className="w-full h-8 text-xs"
        >
          {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
          Request OTP
        </Button>
      ) : (
        <div className="space-y-3">
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

          <Button
            size="sm"
            className="w-full h-8 text-xs"
            onClick={handleVerify}
            disabled={loading || otp.length < 6 || !emailValid}
          >
            {loading && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            Verify OTP
          </Button>

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
