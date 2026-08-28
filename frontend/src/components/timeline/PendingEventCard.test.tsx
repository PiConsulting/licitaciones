import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PendingEventCard } from "./PendingEventCard";
import { Event } from "../../types/timeline";

const createMockPendingEvent = (overrides?: Partial<Event>): Event => ({
  id: "evt-pending-123",
  event_id: "evt-pending-123",
  analysis_id: "analysis-456",
  name: "Adjudicación",
  event_date: null,
  date_source: "pending",
  status: "pending",
  deleted: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

describe("PendingEventCard", () => {
  test("renders pending event with name", () => {
    const event = createMockPendingEvent({ name: "Entrega de equipamiento" });
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} onAddDate={handleAddDate} />);

    expect(screen.getByText("Entrega de equipamiento")).toBeInTheDocument();
    expect(screen.getByText("Fecha pendiente")).toBeInTheDocument();
  });

  test("shows pendiente badge", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} onAddDate={handleAddDate} />);

    expect(screen.getByText("Pendiente")).toBeInTheDocument();
  });

  test("shows add date button", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} onAddDate={handleAddDate} />);

    const button = screen.getByRole("button", { name: /Agregar fecha/i });
    expect(button).toBeInTheDocument();
  });

  test("calls onAddDate when button is clicked", async () => {
    const user = userEvent.setup();
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} onAddDate={handleAddDate} />);

    const button = screen.getByRole("button", { name: /Agregar fecha/i });
    await user.click(button);

    expect(handleAddDate).toHaveBeenCalledTimes(1);
  });

  test("shows dependents warning when hasDependents is true", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} hasDependents={true} onAddDate={handleAddDate} />);

    expect(screen.getByText("Otros eventos dependen de esta fecha")).toBeInTheDocument();
  });

  test("does not show dependents warning when hasDependents is false", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} hasDependents={false} onAddDate={handleAddDate} />);

    expect(screen.queryByText("Otros eventos dependen de esta fecha")).not.toBeInTheDocument();
  });

  test("has correct styling with dashed border", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard event={event} onAddDate={handleAddDate} />);

    const card = screen.getByText("Adjudicación").closest(".pending-event-card");
    expect(card).toHaveClass("border-dashed", "border-gray-300", "bg-gray-50/50");
  });
});
