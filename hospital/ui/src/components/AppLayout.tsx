import { Settings, Activity } from "lucide-react";
import { Link } from "react-router-dom";
import { useHealthCheck } from "@/hooks/use-health-check";
import { cn } from "@/lib/utils";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const health = useHealthCheck();

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-40 border-b bg-card/80 backdrop-blur">
        <div className="container flex h-14 items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-semibold text-primary">
            <Activity className="h-5 w-5" />
            <span>Hospital Booking</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <div
                className={cn(
                  "h-2 w-2 rounded-full",
                  health === "ok" && "bg-[hsl(var(--success))]",
                  health === "error" && "bg-destructive",
                  health === "checking" && "bg-muted-foreground animate-pulse"
                )}
              />
              {health === "ok" ? "Connected" : health === "error" ? "Offline" : "Checking…"}
            </div>
            <Link to="/settings" className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors">
              <Settings className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
