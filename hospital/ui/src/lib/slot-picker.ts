import { format, isValid, parseISO } from "date-fns";
import type { SelectionListItem } from "@/lib/types";

export interface DoctorSlotDayGroup {
  key: string;
  label: string;
  calendarDate: Date;
  slots: SelectionListItem[];
}

export interface DoctorSlotGroup {
  key: string;
  name: string;
  nextAvailableIso: string | null;
  nextAvailableLabel: string;
  slotCount: number;
  dates: DoctorSlotDayGroup[];
}

export function extractDoctorNameFromSlotLabel(label: string): string {
  const [doctorPart] = label.split("•");
  const name = doctorPart?.trim();
  return name && name.length > 0 ? name : "Available doctor";
}

export function dateKeyToCalendarDate(dateKey: string): Date {
  const [year, month, day] = dateKey.split("-").map(Number);
  return new Date(year, month - 1, day, 12, 0, 0, 0);
}

function toDayLabel(dateKey: string): string {
  return format(dateKeyToCalendarDate(dateKey), "EEE d MMM");
}

function getItemIsoDate(item: SelectionListItem): string | null {
  if (item.meta?.isoDate?.trim()) {
    return item.meta.isoDate.trim();
  }

  return null;
}

function formatNextAvailableLabel(isoDate: string | null): string {
  if (!isoDate) {
    return "No open time slots";
  }

  const parsed = parseISO(isoDate);
  if (!isValid(parsed)) {
    return isoDate;
  }

  return format(parsed, "EEE d MMM, h:mm a");
}

export function formatSlotChipLabel(item: SelectionListItem): string {
  const isoDate = getItemIsoDate(item);

  if (isoDate) {
    const parsed = parseISO(isoDate);
    if (isValid(parsed)) {
      return format(parsed, "h:mm a");
    }
  }

  if (item.meta?.startTime?.trim()) {
    return item.meta.startTime
      .replace(/^\d{4}-\d{2}-\d{2}\s*/, "")
      .replace(/\s*UTC$/, "");
  }

  return item.label;
}

export function buildDoctorSlotGroups(
  items: SelectionListItem[],
): DoctorSlotGroup[] {
  const doctorMap = new Map<
    string,
    {
      key: string;
      name: string;
      firstSeenIndex: number;
      nextAvailableIso: string | null;
      dates: Map<string, SelectionListItem[]>;
    }
  >();

  items.forEach((item, index) => {
    const doctorName = extractDoctorNameFromSlotLabel(item.label);
    const isoDate = getItemIsoDate(item);

    if (!isoDate) {
      return;
    }

    const dateKey = isoDate.slice(0, 10);

    if (!doctorMap.has(doctorName)) {
      doctorMap.set(doctorName, {
        key: `doctor:${doctorName}`,
        name: doctorName,
        firstSeenIndex: index,
        nextAvailableIso: isoDate,
        dates: new Map<string, SelectionListItem[]>(),
      });
    }

    const doctor = doctorMap.get(doctorName)!;

    if (!doctor.nextAvailableIso || isoDate < doctor.nextAvailableIso) {
      doctor.nextAvailableIso = isoDate;
    }

    const dateItems = doctor.dates.get(dateKey) ?? [];
    dateItems.push(item);
    doctor.dates.set(dateKey, dateItems);
  });

  return Array.from(doctorMap.values())
    .sort((a, b) => a.firstSeenIndex - b.firstSeenIndex)
    .map((doctor) => {
      const dates: DoctorSlotDayGroup[] = Array.from(doctor.dates.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([dateKey, slots]) => {
          const sortedSlots = [...slots].sort((left, right) => {
            const leftIso = getItemIsoDate(left) ?? "";
            const rightIso = getItemIsoDate(right) ?? "";
            return leftIso.localeCompare(rightIso);
          });

          return {
            key: dateKey,
            label: toDayLabel(dateKey),
            calendarDate: dateKeyToCalendarDate(dateKey),
            slots: sortedSlots,
          };
        });

      const slotCount = dates.reduce(
        (total, dayGroup) => total + dayGroup.slots.length,
        0,
      );

      return {
        key: doctor.key,
        name: doctor.name,
        nextAvailableIso: doctor.nextAvailableIso,
        nextAvailableLabel: formatNextAvailableLabel(doctor.nextAvailableIso),
        slotCount,
        dates,
      };
    });
}