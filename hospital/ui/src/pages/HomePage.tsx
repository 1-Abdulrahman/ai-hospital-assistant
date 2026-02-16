import { Activity, Clock, CheckCircle, Users } from "lucide-react";

export default function HomePage() {
  return (
    <div className="container max-w-2xl py-12 space-y-12">
      <div className="text-center space-y-4">
        <div className="flex justify-center">
          <div className="rounded-full bg-primary/10 p-4">
            <Activity className="h-8 w-8 text-primary" />
          </div>
        </div>
        <h1 className="text-3xl font-bold">Hospital Booking System</h1>
        <p className="text-lg text-muted-foreground max-w-md mx-auto">
          Book your hospital appointment quickly and easily using our AI-powered chat assistant.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="rounded-lg border bg-card p-6 space-y-3">
          <div className="flex items-center gap-3">
            <Clock className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">Easy Scheduling</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Choose your preferred date and time slot. Our system ensures you get the appointment that works best for you.
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 space-y-3">
          <div className="flex items-center gap-3">
            <Users className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">Smart Matching</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Describe your symptoms and our AI will suggest the best specialty to match your needs.
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 space-y-3">
          <div className="flex items-center gap-3">
            <CheckCircle className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">Instant Confirmation</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Get your booking reference immediately with OTP verification for security.
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 space-y-3">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary" />
            <h3 className="font-semibold">Always Available</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Access the booking system 24/7 with our floating chat widget, always ready to help.
          </p>
        </div>
      </div>

      <div className="rounded-lg border bg-accent/50 p-6 text-center space-y-2">
        <p className="font-semibold">Ready to book?</p>
        <p className="text-sm text-muted-foreground">
          Click the chat icon at the bottom right to get started.
        </p>
      </div>
    </div>
  );
}
