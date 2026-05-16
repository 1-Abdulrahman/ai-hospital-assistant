import { fireEvent, render, screen } from "@testing-library/react";
import SelectionList from "@/components/chat/SelectionList";
import type { SelectionList as SelectionListType } from "@/lib/types";

describe("SelectionList", () => {
  const specialtyList: SelectionListType = {
    type: "specialty",
    items: [
      {
        id: "cardiology",
        label: "Cardiology",
        description: "Suggested by symptom interpretation.",
        confidence: 0.91,
      },
      {
        id: "neurology",
        label: "Neurology",
        description: "Alternative specialty.",
        confidence: 0.06,
      },
    ],
  };

  const slotList: SelectionListType = {
    type: "slot",
    items: [
      {
        id: "slot-1",
        label: "Dr. Lina Alharbi • 2026-04-14 09:00:00 UTC",
        description: "Cardiology appointment slot.",
        meta: {
          isoDate: "2026-04-14T09:00:00Z",
          startTime: "2026-04-14 09:00:00 UTC",
          endTime: "09:30:00 UTC",
          timezone: "UTC",
          practitionerRef: "Practitioner/prac-card-1",
          practitionerDisplay: "Dr. Lina Alharbi",
          specialtyId: "cardiology",
          specialtyDisplay: "Cardiology",
          dateKey: "2026-04-14",
          displayDate: "Tue 14 Apr 2026",
          displayTime: "9:00 AM",
          isPreferredPractitioner: true,
        },
      },
      {
        id: "slot-2",
        label: "Dr. Lina Alharbi • 2026-04-14 10:30:00 UTC",
        description: "Cardiology appointment slot.",
        meta: {
          isoDate: "2026-04-14T10:30:00Z",
          startTime: "2026-04-14 10:30:00 UTC",
          endTime: "11:00:00 UTC",
          timezone: "UTC",
          practitionerRef: "Practitioner/prac-card-1",
          practitionerDisplay: "Dr. Lina Alharbi",
          specialtyId: "cardiology",
          specialtyDisplay: "Cardiology",
          dateKey: "2026-04-14",
          displayDate: "Tue 14 Apr 2026",
          displayTime: "10:30 AM",
          isPreferredPractitioner: true,
        },
      },
      {
        id: "slot-3",
        label: "Dr. Omar Salem • 2026-04-15 09:00:00 UTC",
        description: "Cardiology appointment slot.",
        meta: {
          isoDate: "2026-04-15T09:00:00Z",
          startTime: "2026-04-15 09:00:00 UTC",
          endTime: "09:30:00 UTC",
          timezone: "UTC",
          practitionerRef: "Practitioner/prac-card-2",
          practitionerDisplay: "Dr. Omar Salem",
          specialtyId: "cardiology",
          specialtyDisplay: "Cardiology",
          dateKey: "2026-04-15",
          displayDate: "Wed 15 Apr 2026",
          displayTime: "9:00 AM",
          isPreferredPractitioner: false,
        },
      },
    ],
  };

  it("renders specialty items with description and confidence percentage", () => {
    const onSelect = vi.fn();

    render(<SelectionList list={specialtyList} onSelect={onSelect} />);

    expect(screen.getByText("Cardiology")).toBeInTheDocument();
    expect(
      screen.getByText("Suggested by symptom interpretation."),
    ).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();

    expect(screen.getByText("Neurology")).toBeInTheDocument();
    expect(screen.getByText("Alternative specialty.")).toBeInTheDocument();
    expect(screen.getByText("6%")).toBeInTheDocument();
  });

  it("calls onSelect when an enabled specialty item is clicked", () => {
    const onSelect = vi.fn();

    render(<SelectionList list={specialtyList} onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Cardiology"));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "cardiology",
        label: "Cardiology",
      }),
    );
  });

  it("does not call onSelect when specialty list is disabled", () => {
    const onSelect = vi.fn();

    render(
      <SelectionList list={specialtyList} onSelect={onSelect} disabled />,
    );

    fireEvent.click(screen.getByText("Cardiology"));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("renders a doctor-first availability picker for slot lists", () => {
    const onSelect = vi.fn();

    render(<SelectionList list={slotList} onSelect={onSelect} />);

    expect(screen.getByText("Choose a doctor")).toBeInTheDocument();
    expect(screen.getAllByText("Dr. Lina Alharbi")).toHaveLength(2);
    expect(screen.getByText("Dr. Omar Salem")).toBeInTheDocument();
    expect(screen.getByText("Open time slots")).toBeInTheDocument();
    expect(screen.getAllByText("Continuity priority").length).toBeGreaterThan(0);
  });

  it("selects a time slot from the doctor-first picker", () => {
    const onSelect = vi.fn();

    render(<SelectionList list={slotList} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /10:30/i }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "slot-2",
        label: "Dr. Lina Alharbi • 2026-04-14 10:30:00 UTC",
      }),
    );
  });

  it("marks the selected specialty visually", () => {
    const onSelect = vi.fn();

    const { container } = render(
      <SelectionList
        list={specialtyList}
        onSelect={onSelect}
        selectedId="cardiology"
      />,
    );

    const selectedCard = container.querySelector(".ring-2");
    expect(selectedCard).toBeTruthy();
  });
});