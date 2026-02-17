import { useState } from "react";
import { Loader2, Mail, ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { requestOtp, verifyOtp, chatConfirm } from "@/lib/api-client";
import { toast } from "sonner";

export default function ChatWidgetOtp() {
  const [otp, setOtp] = useState("");
  const [otpRequested, setOtpRequested] = useState(false);
  const [loading, setLoading] = useState(false);
  const { currentMode, renewalItemId, setOtpVerified, setStep, addMessage } = useBookingFlow();

  const handleRequestOtp = async () => {
    setLoading(true);
    try {
      await requestOtp();
      setOtpRequested(true);
      toast.success("OTP sent to MailHog!");
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    if (otp.length < 6) return;
    setLoading(true);
    try {
      const res = await verifyOtp(otp);
      if (res.verified) {
        setOtpVerified(true);
        if (currentMode === "renewal") {
          // For renewal: confirm immediately and return to chat
          const confirmRes = await chatConfirm({
            action: "CONFIRM_RENEWAL",
            renewalItemId: renewalItemId || undefined,
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
        toast.error("Invalid OTP. Please try again.");
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3">
      <h3 className="font-semibold text-sm mb-3">Verify Your Identity</h3>

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
        <Button size="sm" onClick={handleRequestOtp} disabled={loading} className="w-full h-8 text-xs">
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
            disabled={loading || otp.length < 6}
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
