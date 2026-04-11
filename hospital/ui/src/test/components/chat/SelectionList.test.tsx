import { render, screen, fireEvent } from "@testing-library/react";
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
        label: "Dr. Lina Alharbi • 2026-04-12 09:00:00 UTC",
        description: "Cardiology appointment slot.",
        meta: {
          isoDate: "2026-04-12T09:00:00Z",
          startTime: "2026-04-12 09:00:00 UTC",
          endTime: "09:30:00 UTC",
          timezone: "UTC",
        },
      },
    ],
  };

  it("renders specialty items with description and confidence percentage", () => {
    const onSelect = vi.fn();

    render(
      <SelectionList
        list={specialtyList}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByText("Cardiology")).toBeInTheDocument();
    expect(screen.getByText("Suggested by symptom interpretation.")).toBeInTheDocument();
    expect(screen.getByText("91%")).toBeInTheDocument();

    expect(screen.getByText("Neurology")).toBeInTheDocument();
    expect(screen.getByText("Alternative specialty.")).toBeInTheDocument();
    expect(screen.getByText("6%")).toBeInTheDocument();
  });

  it("calls onSelect when an enabled item is clicked", () => {
    const onSelect = vi.fn();

    render(
      <SelectionList
        list={specialtyList}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByText("Cardiology"));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "cardiology",
        label: "Cardiology",
      }),
    );
  });

  it("does not call onSelect when disabled", () => {
    const onSelect = vi.fn();

    render(
      <SelectionList
        list={specialtyList}
        onSelect={onSelect}
        disabled
      />,
    );

    fireEvent.click(screen.getByText("Cardiology"));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("renders slot items without specialty confidence percentages", () => {
    const onSelect = vi.fn();

    render(
      <SelectionList
        list={slotList}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByText("Dr. Lina Alharbi • 2026-04-12 09:00:00 UTC")).toBeInTheDocument();
    expect(screen.getByText("Cardiology appointment slot.")).toBeInTheDocument();
    expect(screen.queryByText("91%")).not.toBeInTheDocument();
  });

  it("marks the selected item visually", () => {
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