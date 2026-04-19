import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Clock3, UserRound } from "lucide-react";
import { format } from "date-fns";

import type { SelectionList as SelectionListType, SelectionListItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import {
  buildDoctorSlotGroups,
  dateKeyToCalendarDate,
  formatSlotChipLabel,
} from "@/lib/slot-picker";

interface DoctorAvailabilityPickerProps {
  list: SelectionListType;
  onSelect: (item: SelectionListItem) => void;
  selectedId?: string | null;
  disabled?: boolean;
}

export default function DoctorAvailabilityPicker({
  list,
  onSelect,
  selectedId,
  disabled,
}: DoctorAvailabilityPickerProps) {
  const doctorGroups = useMemo(() => buildDoctorSlotGroups(list.items), [list.items]);

  const [selectedDoctorKey, setSelectedDoctorKey] = useState<string | null>(null);
  const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);

  useEffect(() => {
    if (doctorGroups.length === 0) {
      setSelectedDoctorKey(null);
      return;
    }

    const doctorStillExists = doctorGroups.some((doctor) => doctor.key === selectedDoctorKey);

    if (!selectedDoctorKey || !doctorStillExists) {
      setSelectedDoctorKey(doctorGroups[0].key);
    }
  }, [doctorGroups, selectedDoctorKey]);

  const selectedDoctor = useMemo(
    () => doctorGroups.find((doctor) => doctor.key === selectedDoctorKey) ?? null,
    [doctorGroups, selectedDoctorKey],
  );

  useEffect(() => {
    if (!selectedDoctor || selectedDoctor.dates.length === 0) {
      setSelectedDateKey(null);
      return;
    }

    const dateStillExists = selectedDoctor.dates.some((dateGroup) => dateGroup.key === selectedDateKey);

    if (!selectedDateKey || !dateStillExists) {
      setSelectedDateKey(selectedDoctor.dates[0].key);
    }
  }, [selectedDoctor, selectedDateKey]);

  const selectedDateGroup = useMemo(
    () => selectedDoctor?.dates.find((dateGroup) => dateGroup.key === selectedDateKey) ?? null,
    [selectedDoctor, selectedDateKey],
  );

  const selectedCalendarDate = selectedDateKey ? dateKeyToCalendarDate(selectedDateKey) : undefined;

  const availableDateKeys = useMemo(
    () => new Set(selectedDoctor?.dates.map((dateGroup) => dateGroup.key) ?? []),
    [selectedDoctor],
  );

  const handleCalendarSelect = (date?: Date) => {
    if (!date || !selectedDoctor) {
      return;
    }

    const key = format(date, "yyyy-MM-dd");
    if (availableDateKeys.has(key)) {
      setSelectedDateKey(key);
    }
  };

  if (doctorGroups.length === 0) {
    return (
      <div className="mt-2 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        No doctors or time slots are available right now.
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-3">
      <div className="rounded-lg border bg-background/70 p-3">
        <div className="mb-3">
          <p className="text-xs font-semibold">Choose a doctor</p>
          <p className="text-[10px] text-muted-foreground mt-1">
            Select a doctor first, then choose a date and open time slot.
          </p>
        </div>

        <div className="grid gap-2">
          {doctorGroups.map((doctor) => {
            const isSelected = doctor.key === selectedDoctorKey;

            return (
              <button
                key={doctor.key}
                type="button"
                disabled={disabled}
                onClick={() => setSelectedDoctorKey(doctor.key)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left transition-colors",
                  "hover:bg-accent/40",
                  isSelected && "border-primary bg-accent/50 ring-1 ring-primary",
                  disabled && "pointer-events-none opacity-50",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <UserRound className="h-4 w-4 text-muted-foreground shrink-0" />
                      <p className="text-sm font-medium truncate">{doctor.name}</p>
                    </div>

                    <p className="mt-1 text-xs text-muted-foreground">
                      Next available: {doctor.nextAvailableLabel}
                    </p>
                  </div>

                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {doctor.isPreferredDoctor && (
                      <Badge variant="secondary" className="text-[10px]">
                        Continuity priority
                      </Badge>
                    )}
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

      {selectedDoctor && (
        <div className="rounded-lg border bg-background/70 p-3 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-muted-foreground" />
                <p className="text-xs font-semibold">{selectedDoctor.name}</p>
              </div>
              <p className="mt-1 text-[10px] text-muted-foreground">
                Pick a date, then choose one of the open appointment times.
              </p>
            </div>

            <div className="flex flex-col items-end gap-1 shrink-0">
              {selectedDoctor.isPreferredDoctor && (
                <Badge variant="secondary" className="text-[10px]">
                  Continuity priority
                </Badge>
              )}
              <Badge variant="outline" className="text-[10px]">
                {selectedDoctor.slotCount} open
              </Badge>
            </div>
          </div>

          <div className="rounded-md border bg-muted/20">
            <Calendar
              mode="single"
              selected={selectedCalendarDate}
              onSelect={handleCalendarSelect}
              disabled={(date) => !availableDateKeys.has(format(date, "yyyy-MM-dd"))}
              className="mx-auto w-fit"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {selectedDoctor.dates.map((dateGroup) => {
              const isSelected = selectedDateKey === dateGroup.key;

              return (
                <Button
                  key={dateGroup.key}
                  type="button"
                  size="sm"
                  variant={isSelected ? "default" : "outline"}
                  className="h-8 text-xs"
                  onClick={() => setSelectedDateKey(dateGroup.key)}
                  disabled={disabled}
                >
                  {dateGroup.label}
                </Button>
              );
            })}
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Clock3 className="h-4 w-4 text-muted-foreground" />
              <p className="text-xs font-semibold">Open time slots</p>
            </div>

            {selectedDateGroup ? (
              <div className="flex flex-wrap gap-2">
                {selectedDateGroup.slots.map((slot) => {
                  const isSelected = selectedId === slot.id;

                  return (
                    <Button
                      key={slot.id}
                      type="button"
                      size="sm"
                      variant={isSelected ? "default" : "outline"}
                      className="h-8 text-xs"
                      onClick={() => onSelect(slot)}
                      disabled={disabled}
                    >
                      {formatSlotChipLabel(slot)}
                    </Button>
                  );
                })}
              </div>
            ) : (
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