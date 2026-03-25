import { useState, useEffect, useRef } from "react";
import { X, Minus, MessageCircle, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useWidgetState } from "@/hooks/use-widget-state";
import { useHealthCheck } from "@/hooks/use-health-check";
import { cn } from "@/lib/utils";
import ChatWidgetContent from "./ChatWidgetContent";

export default function ChatWidget() {
  const { isOpen, isMinimized, setIsOpen, setIsMinimized } = useWidgetState();
  const health = useHealthCheck();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
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
  }, [isOpen, setIsOpen]);

  return (
    <>
      {isOpen && !isMinimized && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setIsOpen(false)} />
      )}

      <div
        ref={panelRef}
        className={cn(
          "fixed bottom-4 right-4 z-50 flex flex-col bg-card rounded-xl border shadow-lg transition-all duration-300",
          isOpen && !isMinimized
            ? "w-full h-[85vh] sm:w-[380px] sm:h-[560px] opacity-100 scale-100"
            : "w-14 h-14 opacity-0 scale-0 pointer-events-none"
        )}
      >
        {isOpen && !isMinimized && (
          <>
            <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <Activity className="h-4 w-4 text-primary shrink-0" />
                <span className="font-semibold text-sm truncate">Hospital Booking</span>
              </div>
              <div className="flex items-center gap-1 shrink-0 ml-2">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <div
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      health === "ok" && "bg-[hsl(var(--success))]",
                      health === "error" && "bg-destructive",
                      health === "checking" && "bg-muted-foreground animate-pulse"
                    )}
                  />
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={() => setIsMinimized(true)}
                >
                  <Minus className="h-3 w-3" />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7"
                  onClick={() => setIsOpen(false)}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden">
              <ChatWidgetContent />
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
          className={cn(
            "fixed bottom-4 right-4 z-50 flex items-center justify-center h-14 w-14 rounded-full bg-primary text-primary-foreground shadow-lg hover:shadow-xl hover:scale-110 transition-all duration-200"
          )}
          aria-label="Open chat"
        >
          <MessageCircle className="h-5 w-5" />
        </button>
      )}
    </>
  );
}
