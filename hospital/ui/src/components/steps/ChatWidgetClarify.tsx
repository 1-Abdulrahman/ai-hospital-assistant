import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useBookingFlow } from "@/hooks/use-booking-flow";
import { ChevronLeft } from "lucide-react";
import type { SpecialtyCandidate } from "@/lib/types";

interface ChatWidgetClarifyProps {
  candidates: SpecialtyCandidate[];
}

export default function ChatWidgetClarify({ candidates }: ChatWidgetClarifyProps) {
  const { setSelectedSpecialty, setStep } = useBookingFlow();

  const handleSelect = (label: string) => {
    setSelectedSpecialty(label);
    setStep("book");
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-3 space-y-3">
      <h3 className="font-semibold text-sm">Which specialty fits best?</h3>
      <p className="text-xs text-muted-foreground">Select one to continue.</p>
      <div className="space-y-2">
        {candidates.slice(0, 3).map((c) => (
          <Card
            key={c.label}
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => handleSelect(c.label)}
          >
            <CardContent className="flex items-center gap-2 p-3">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium capitalize">{c.label}</p>
                <Progress value={c.p * 100} className="mt-1 h-1.5" />
              </div>
              <span className="text-xs font-medium text-muted-foreground shrink-0">
                {Math.round(c.p * 100)}%
              </span>
            </CardContent>
          </Card>
        ))}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="w-full text-xs justify-start"
        onClick={() => setStep("chat")}
      >
        <ChevronLeft className="h-3 w-3 mr-1" />
        Back to chat
      </Button>
    </div>
  );
}
