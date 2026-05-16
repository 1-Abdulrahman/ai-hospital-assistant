import { Check } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type {
  SelectionList as SelectionListType,
  SelectionListItem,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import DoctorAvailabilityPicker from "./DoctorAvailabilityPicker";

/**
 * Props for the SelectionList component
 */
interface SelectionListProps {
  /** The selection list data containing items and type information */
  list: SelectionListType;
  /** Callback fired when a user selects an item from the list */
  onSelect: (item: SelectionListItem) => void;
  /** ID of the currently selected item, if any */
  selectedId?: string | null;
  /** Whether the list is disabled and not interactive */
  disabled?: boolean;
}

/**
 * Renders a backend-provided SelectionList inline in the chat thread.
 * 
 * Supports different list types:
 * - "slot": Uses a doctor-first availability picker to condense many time slots
 * - Other types (e.g., "specialty"): Rendered as individual selectable cards
 * 
 * @param list - The selection list data from backend
 * @param onSelect - Callback when user selects an item
 * @param selectedId - ID of currently selected item for visual indication
 * @param disabled - If true, disables all interactions
 * @returns Rendered selection list component
 */
export default function SelectionList({
  list,
  onSelect,
  selectedId,
  disabled,
}: SelectionListProps) {
  // Use specialized DoctorAvailabilityPicker for slot lists to avoid cluttering chat
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

  // Render other list types as individual selectable cards
  return (
    <div className="mt-2 space-y-1.5">
      {list.items.map((item) => {
        // Determine if this item is currently selected
        const isSelected = selectedId === item.id;

        return (
          <Card
            key={item.id}
            className={cn(
              // Base styles: cursor indicates interactivity, hover provides feedback
              "cursor-pointer transition-shadow hover:shadow-md",
              // Highlight selected item with a primary-colored ring
              isSelected && "ring-2 ring-primary",
              // Reduce opacity and disable interactions when disabled
              disabled && "opacity-50 pointer-events-none",
            )}
            onClick={() => !disabled && onSelect(item)}
          >
            <CardContent className="flex items-center gap-2 p-2.5">
              {/* Item content: label, optional description, and confidence indicator */}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium capitalize">{item.label}</p>

                {/* Show optional description text if provided */}
                {item.description && (
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {item.description}
                  </p>
                )}

                {/* For specialty lists, display confidence level as a progress bar */}
                {list.type === "specialty" && item.confidence != null && (
                  <Progress
                    value={item.confidence * 100}
                    className="mt-1 h-1.5"
                  />
                )}
              </div>

              {/* Display confidence percentage for specialty items */}
              {list.type === "specialty" && item.confidence != null && (
                <span className="text-xs font-medium text-muted-foreground shrink-0">
                  {Math.round(item.confidence * 100)}%
                </span>
              )}

              {/* Show checkmark icon when item is selected */}
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