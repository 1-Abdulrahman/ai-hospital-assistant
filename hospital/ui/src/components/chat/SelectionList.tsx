import { Check } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type {
  SelectionList as SelectionListType,
  SelectionListItem,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import DoctorAvailabilityPicker from "./DoctorAvailabilityPicker";

interface SelectionListProps {
  list: SelectionListType;
  onSelect: (item: SelectionListItem) => void;
  selectedId?: string | null;
  disabled?: boolean;
}

/**
 * Renders a backend-provided SelectionList inline in the chat thread.
 * Slot lists use a doctor-first availability picker to avoid flooding
 * the chat with too many individual slot cards.
 */
export default function SelectionList({
  list,
  onSelect,
  selectedId,
  disabled,
}: SelectionListProps) {
  if (list.type === "slot") {
    return (
      <DoctorAvailabilityPicker
        list={list}
        onSelect={onSelect}
        selectedId={selectedId}
        disabled={disabled}
      />
    );
  }

  return (
    <div className="mt-2 space-y-1.5">
      {list.items.map((item) => {
        const isSelected = selectedId === item.id;

        return (
          <Card
            key={item.id}
            className={cn(
              "cursor-pointer transition-shadow hover:shadow-md",
              isSelected && "ring-2 ring-primary",
              disabled && "opacity-50 pointer-events-none",
            )}
            onClick={() => !disabled && onSelect(item)}
          >
            <CardContent className="flex items-center gap-2 p-2.5">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium capitalize">{item.label}</p>

                {item.description && (
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {item.description}
                  </p>
                )}

                {list.type === "specialty" && item.confidence != null && (
                  <Progress
                    value={item.confidence * 100}
                    className="mt-1 h-1.5"
                  />
                )}
              </div>

              {list.type === "specialty" && item.confidence != null && (
                <span className="text-xs font-medium text-muted-foreground shrink-0">
                  {Math.round(item.confidence * 100)}%
                </span>
              )}

              {isSelected && (
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}