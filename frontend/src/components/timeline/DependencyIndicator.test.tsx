import { render, screen } from "@testing-library/react";
import { DependencyIndicator } from "./DependencyIndicator";
import { Deadline, Event } from "../../types/timeline";

const createMockDeadline = (overrides?: Partial<Deadline>): Deadline => ({
  id: "deadline-123",
  deadline_id: "deadline-123",
  analysis_id: "analysis-456",
  trigger_event_id: "event-trigger",
  target_event_id: "event-target",
  duration: 45,
  unit: "días",
  day_type: "corridos",
  calculated_date: null,
  calculation_status: "pending",
  deleted: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

const createMockTriggerEvent = (overrides?: Partial<Event>): Event => ({
  id: "event-trigger",
  event_id: "event-trigger",
  analysis_id: "analysis-456",
  name: "Adjudicación",
  event_date: "2026-09-10",
  date_source: "detected",
  status: "confirmed",
  deleted: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

describe("DependencyIndicator", () => {
  test("shows dependency from trigger event with date", () => {
    const deadline = createMockDeadline({ duration: 45, day_type: "corridos" });
    const triggerEvent = createMockTriggerEvent({ name: "Adjudicación" });

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    expect(screen.getByText(/45 días corridos desde Adjudicación/)).toBeInTheDocument();
  });

  test("shows hábiles day type correctly", () => {
    const deadline = createMockDeadline({ duration: 30, day_type: "hábiles" });
    const triggerEvent = createMockTriggerEvent({ name: "Apertura de ofertas" });

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    expect(screen.getByText(/30 días hábiles desde Apertura de ofertas/)).toBeInTheDocument();
  });

  test("shows no_especificado day type correctly", () => {
    const deadline = createMockDeadline({ duration: 15, day_type: "no_especificado" });
    const triggerEvent = createMockTriggerEvent({ name: "Publicación" });

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    expect(
      screen.getByText(/15 días \(tipo no especificado\) desde Publicación/)
    ).toBeInTheDocument();
  });

  test("shows pending when trigger event has no date", () => {
    const deadline = createMockDeadline();
    const triggerEvent = createMockTriggerEvent({ name: "Adjudicación", event_date: null });

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    expect(screen.getByText("Pendiente de fecha de Adjudicación")).toBeInTheDocument();
  });

  test("shows pending when no trigger event provided", () => {
    const deadline = createMockDeadline();

    render(<DependencyIndicator deadline={deadline} triggerEvent={undefined} />);

    expect(screen.getByText("Pendiente de fecha de evento anterior")).toBeInTheDocument();
  });

  test("has correct styling for confirmed dependency", () => {
    const deadline = createMockDeadline();
    const triggerEvent = createMockTriggerEvent();

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    const container = screen.getByText(/45 días corridos/).closest("div");
    expect(container).toHaveClass("text-gray-600");
  });

  test("has correct styling for pending dependency", () => {
    const deadline = createMockDeadline();
    const triggerEvent = createMockTriggerEvent({ event_date: null });

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    const container = screen.getByText(/Pendiente de fecha/).closest("div");
    expect(container).toHaveClass("text-gray-500");
  });
});
