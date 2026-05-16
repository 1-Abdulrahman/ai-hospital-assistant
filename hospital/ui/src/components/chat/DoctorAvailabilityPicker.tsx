// React hooks for state management and side effects
import { useEffect, useMemo, useState } from "react";

// Icons from lucide-react
// CalendarDays: calendar icon for date picker section
// Clock3: clock icon for time slots section
// UserRound: doctor/person icon for doctor selection
import { CalendarDays, Clock3, UserRound } from "lucide-react";

// Date formatting utility
import { format } from "date-fns";

// Type definitions for selection lists and items
import type { SelectionList as SelectionListType, SelectionListItem } from "@/lib/types";

// Utility function for conditional CSS class names
import { cn } from "@/lib/utils";

// UI components from shadcn/ui library
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";

// Slot picker utilities: group doctors/dates/slots and format display labels
import {
  // Groups available slots hierarchically: doctors → dates → time slots
  buildDoctorSlotGroups,
  // Converts date string key (YYYY-MM-DD) back to JavaScript Date for Calendar
  dateKeyToCalendarDate,
  // Formats slot time display for button label (e.g., "2:30 PM")
  formatSlotChipLabel,
} from "@/lib/slot-picker";

// Props interface for DoctorAvailabilityPicker component
interface DoctorAvailabilityPickerProps {
  // Selection list containing doctor availability data from backend
  // Structure: array of items with doctor info, dates, time slots, and IDs
  list: SelectionListType;
  
  // Callback fired when user selects a time slot
  // Passes the selected slot item with all booking data
  onSelect: (item: SelectionListItem) => void;
  
  // Optional: ID of currently selected slot (for highlighting in UI)
  selectedId?: string | null;
  
  // Optional: disable all selection interactions (show loading/disabled state)
  disabled?: boolean;
}

/**
 * Doctor Availability Picker: multi-stage selector for booking appointments.
 * 
 * User flow:
 * 1. Select a doctor from available doctors list (shows name, next availability, open slot count)
 * 2. Select a date from calendar or date buttons (only enables dates with available slots)
 * 3. Select a time slot from the chosen doctor's available times on that date
 * 
 * Key behavior:
 * - Maintains stable selections: if a doctor/date disappears from data, automatically falls back to first available
 * - Prevents invalid selections: calendar disables dates without slots, slots show only for selected date
 * - Highlights preferred doctors: shows "Continuity priority" badge for doctors with patient history
 * - Responsive layout: adapts to different screen sizes using Tailwind grid/flex utilities
 */
export default function DoctorAvailabilityPicker({
  list,
  onSelect,
  selectedId,
  disabled,
}: DoctorAvailabilityPickerProps) {
  // Memoized groups: transforms flat list of items into hierarchical structure
  // Structure: array of doctors, each with array of dates, each with array of time slots
  // Recalculates only when list.items changes
  const doctorGroups = useMemo(
    () => buildDoctorSlotGroups(list.items),
    [list.items],
  );

  // Local state: currently selected doctor key (used to filter available dates)
  // Key format: unique doctor identifier (e.g., "doctor-123")
  const [selectedDoctorKey, setSelectedDoctorKey] = useState<string | null>(null);
  
  // Local state: currently selected date key (used to filter available time slots)
  // Key format: date string (e.g., "2024-05-15")
  const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);

  // Effect: maintain stable doctor selection or default to first doctor
  // Problem solved: when backend data updates (doctor becomes unavailable),
  //   prevent showing a deleted doctor or null state
  // Solution: auto-select first available doctor if current selection disappeared
  // Triggers: when doctorGroups changes (new data loaded) or selection changes
  useEffect(() => {
    // Handle empty state: no doctors available at all
    if (doctorGroups.length === 0) {
      setSelectedDoctorKey(null);
      return;
    }

    // Check if current selection still exists in updated data
    const doctorStillExists = doctorGroups.some(
      (doctor) => doctor.key === selectedDoctorKey,
    );

    // Auto-select first doctor if no selection or selection disappeared
    if (!selectedDoctorKey || !doctorStillExists) {
      setSelectedDoctorKey(doctorGroups[0].key);
    }
  }, [doctorGroups, selectedDoctorKey]);

  // Memoized value: get full doctor object from selected key
  // Used to access doctor dates, slot count, preferred status, etc.
  // Returns null if no doctor selected or key doesn't match any doctor
  const selectedDoctor = useMemo(
    () => doctorGroups.find((doctor) => doctor.key === selectedDoctorKey) ?? null,
    [doctorGroups, selectedDoctorKey],
  );

  // Effect: maintain stable date selection as doctor changes
  // Problem solved: when user switches doctors, prevent showing invalid date
  //   (date valid for previous doctor but not for new doctor)
  // Solution: auto-select first available date for new doctor if selection invalid
  // Triggers: when selectedDoctor changes or date selection changes
  useEffect(() => {
    // Handle invalid state: no doctor selected or doctor has no dates
    if (!selectedDoctor || selectedDoctor.dates.length === 0) {
      setSelectedDateKey(null);
      return;
    }

    // Check if current date selection is valid for new doctor
    const dateStillExists = selectedDoctor.dates.some(
      (dateGroup) => dateGroup.key === selectedDateKey,
    );

    // Auto-select first available date for new doctor if no selection or invalid
    if (!selectedDateKey || !dateStillExists) {
      setSelectedDateKey(selectedDoctor.dates[0].key);
    }
  }, [selectedDoctor, selectedDateKey]);

  // Memoized value: get full date group object (contains all time slots for selected date)
  // Used to display time slot buttons for currently selected doctor and date
  // Returns null if no date selected or key doesn't match any date in selected doctor
  const selectedDateGroup = useMemo(
    () =>
      selectedDoctor?.dates.find((dateGroup) => dateGroup.key === selectedDateKey) ??
      null,
    [selectedDoctor, selectedDateKey],
  );

  // Convert selected date key back to JavaScript Date object
  // Needed because Calendar component requires Date type, but slots are keyed by "YYYY-MM-DD" strings
  // Returns undefined if no date selected (prevents Calendar from showing pre-selected date)
  const selectedCalendarDate = selectedDateKey
    ? dateKeyToCalendarDate(selectedDateKey)
    : undefined;

  // Memoized set: dates available for currently selected doctor
  // Used by Calendar component to disable dates that don't have available slots
  // Format: Set of "YYYY-MM-DD" strings (efficient O(1) lookup vs array)
  // Empty set if no doctor selected
  const availableDateKeys = useMemo(
    () => new Set(selectedDoctor?.dates.map((dateGroup) => dateGroup.key) ?? []),
    [selectedDoctor],
  );

  // Handler: user clicked a date in the calendar widget
  // Validates selected date is available for current doctor, then updates selected date
  const handleCalendarSelect = (date?: Date) => {
    // Validation: ensure date was passed and a doctor is selected
    if (!date || !selectedDoctor) {
      return;
    }

    // Convert Date to "YYYY-MM-DD" format for comparison with available dates
    const key = format(date, "yyyy-MM-dd");
    
    // Only allow selection if date has available slots for current doctor
    // Prevents selecting a date with no open times (calendar already disables these visually)
    if (availableDateKeys.has(key)) {
      setSelectedDateKey(key);
    }
  };

  // Conditional rendering: show empty state if no doctors available
  // Handles backend error, no results from search, or all doctors fully booked
  if (doctorGroups.length === 0) {
    return (
      <div className="mt-2 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        No doctors or time slots are available right now.
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-3">
      {/* Section 1: Doctor selection list */}
      <div className="rounded-lg border bg-background/70 p-3">
        {/* Header and instructions */}
        <div className="mb-3">
          <p className="text-xs font-semibold">Choose a doctor</p>
          <p className="text-[10px] text-muted-foreground mt-1">
            Select a doctor first, then choose a date and open time slot.
          </p>
        </div>

        {/* Grid of doctor buttons: each shows name, next availability, slot count */}
        <div className="grid gap-2">
          {doctorGroups.map((doctor, index) => {
            const isSelected = doctor.key === selectedDoctorKey;

            return (
              // Doctor selection button
              <button
                key={doctor.key}
                type="button"
                disabled={disabled}
                onClick={() => setSelectedDoctorKey(doctor.key)}
                // Styling: highlight selected doctor with border and ring
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition-colors",
                  "hover:bg-accent/40",
                  // Selected state: primary border, accent background, visible ring
                  isSelected && "border-primary bg-accent/50 ring-1 ring-primary",
                  // Disabled state: reduce opacity and prevent interactions
                  disabled && "pointer-events-none opacity-50",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  {/* Left section: doctor name and next available time */}
                  <div className="min-w-0">
                    {/* Doctor name with icon */}
                    <div className="flex items-center gap-2">
                      <UserRound className="h-4 w-4 text-muted-foreground shrink-0" />
                      <p className="text-sm font-medium truncate">{doctor.name}</p>
                    </div>

                    {/* Next available date/time for this doctor */}
                    <p className="mt-1 text-xs text-muted-foreground">
                      Next available: {doctor.nextAvailableLabel}
                    </p>
                  </div>

                  {/* Right section: continuity badge and open slot count */}
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {/* Continuity badge: shown if patient has history with this doctor */}
                    {doctor.isPreferredDoctor && (
                      <Badge variant="secondary" className="text-[10px]">
                        Continuity priority
                      </Badge>
                    )}
                    {/* Open slot count badge */}
                    <Badge variant="outline" className="text-[10px]">
                      {doctor.slotCount} open
                    </Badge>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Section 2: Date and time slot selection (shown after doctor selected) */}
      {selectedDoctor && (
        <div className="rounded-lg border bg-background/70 p-3 space-y-3">
          {/* Header with selected doctor name and availability stats */}
          <div className="flex items-start justify-between gap-3">
            <div>
              {/* Header: selected doctor name with calendar icon */}
              <div className="flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-muted-foreground" />
                <p className="text-xs font-semibold">{selectedDoctor.name}</p>
              </div>
              {/* Subtext: instructions for user */}
              <p className="mt-1 text-[10px] text-muted-foreground">
                Pick a date, then choose one of the open appointment times.
              </p>
            </div>

            {/* Doctor stats: continuity badge and total open slots */}
            <div className="flex flex-col items-end gap-1 shrink-0">
              {/* Continuity badge: shown if patient has history with this doctor */}
              {selectedDoctor.isPreferredDoctor && (
                <Badge variant="secondary" className="text-[10px]">
                  Continuity priority
                </Badge>
              )}
              {/* Total open slot count for this doctor across all dates */}
              <Badge variant="outline" className="text-[10px]">
                {selectedDoctor.slotCount} open
              </Badge>
            </div>
          </div>

          {/* Calendar widget: visual date picker */}
          <div className="rounded-md border bg-muted/20">
            <Calendar
              mode="single"
              // Currently selected date (visually highlighted)
              selected={selectedCalendarDate}
              // Callback when user clicks a date
              onSelect={handleCalendarSelect}
              // Disable dates that don't have available slots for selected doctor
              disabled={(date) =>
                !availableDateKeys.has(format(date, "yyyy-MM-dd"))
              }
              className="mx-auto w-fit"
            />
          </div>

          {/* Quick date buttons: alternative to calendar for selecting dates */}
          <div className="flex flex-wrap gap-2">
            {selectedDoctor.dates.map((dateGroup) => {
              // Highlight currently selected date
              const isSelected = selectedDateKey === dateGroup.key;

              return (
                // Date quick-select button
                <Button
                  key={dateGroup.key}
                  type="button"
                  size="sm"
                  // Fill button if selected, outline if not
                  variant={isSelected ? "default" : "outline"}
                  className="h-8 text-xs"
                  // Update selected date when clicked
                  onClick={() => setSelectedDateKey(dateGroup.key)}
                  disabled={disabled}
                >
                  {/* Date label (e.g., "May 15") */}
                  {dateGroup.label}
                </Button>
              );
            })}
          </div>

          {/* Time slot selection: shows available times for selected date and doctor */}
          <div className="space-y-2">
            {/* Header with clock icon and title */}
            <div className="flex items-center gap-2">
              <Clock3 className="h-4 w-4 text-muted-foreground" />
              <p className="text-xs font-semibold">Open time slots</p>
            </div>

            {/* Conditional: show time slots if date selected, otherwise show prompt */}
            {selectedDateGroup ? (
              // Time slot buttons: user clicks one to book
              <div className="flex flex-wrap gap-2">
                {selectedDateGroup.slots.map((slot) => {
                  // Highlight currently selected time slot
                  const isSelected = selectedId === slot.id;

                  return (
                    // Time slot button
                    <Button
                      key={slot.id}
                      type="button"
                      size="sm"
                      // Fill button if selected, outline if not
                      variant={isSelected ? "default" : "outline"}
                      className="h-8 text-xs"
                      // Fire onSelect callback with slot data when clicked
                      onClick={() => onSelect(slot)}
                      disabled={disabled}
                    >
                      {/* Time label (e.g., "2:30 PM") */}
                      {formatSlotChipLabel(slot)}
                    </Button>
                  );
                })}
              </div>
            ) : (
              // Prompt to select a date first
              <p className="text-xs text-muted-foreground">
                Select a date to view open times.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}