import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EventCard, ConfirmedEvent } from "./EventCard";
import { Deadline } from "../../types/timeline";

const createMockEvent = (overrides?: Partial<ConfirmedEvent>): ConfirmedEvent => ({
  id: "evt-123",
  event_id: "evt-123",
  analysis_id: "analysis-456",
  name: "Apertura de ofertas",
  event_date: "2026-09-15", // Siempre string (ConfirmedEvent)
  date_source: "detected",
  status: "confirmed",
  deleted: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

describe("EventCard", () => {
  test("renders event with detected date", () => {
    const event = createMockEvent({
      name: "Adjudicación",
      event_date: "2026-09-10",
      date_source: "detected",
    });

    render(<EventCard event={event} />);

    expect(screen.getByText("Adjudicación")).toBeInTheDocument();
    expect(screen.getByText("10/09/2026")).toBeInTheDocument();
    expect(screen.getByText("Detectada")).toBeInTheDocument();
  });

  test("renders event with user_input date", () => {
    const event = createMockEvent({
      name: "Presentación de consultas",
      event_date: "2026-08-30",
      date_source: "user_input",
    });

    render(<EventCard event={event} />);

    expect(screen.getByText("Presentación de consultas")).toBeInTheDocument();
    expect(screen.getByText("30/08/2026")).toBeInTheDocument();
    expect(screen.getByText("Ingresada")).toBeInTheDocument();
  });

  test("renders event with calculated date", () => {
    const event = createMockEvent({
      name: "Cierre de consultas",
      event_date: "2026-09-05",
      date_source: "calculated",
    });

    render(<EventCard event={event} />);

    expect(screen.getByText("Cierre de consultas")).toBeInTheDocument();
    expect(screen.getByText("05/09/2026")).toBeInTheDocument();
    expect(screen.getByText("Calculada")).toBeInTheDocument();
  });

  test("calls onClick when card is clicked", async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();
    const event = createMockEvent();

    render(<EventCard event={event} onClick={handleClick} />);

    const card = screen.getByText("Apertura de ofertas").closest(".event-card");
    if (!card) throw new Error("Card not found");

    await user.click(card);

    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  test("has correct styling and structure", () => {
    const event = createMockEvent();

    render(<EventCard event={event} />);

    const card = screen.getByText("Apertura de ofertas").closest(".event-card");
    expect(card).toHaveClass("rounded-lg", "border", "p-4", "cursor-pointer");
  });

  test("shows dependency indicator when deadline and triggerEvent provided", () => {
    const event = createMockEvent({ name: "Entrega equipamiento" });
    const deadline: Deadline = {
      id: "deadline-1",
      deadline_id: "deadline-1",
      analysis_id: "analysis-456",
      target_event_id: event.event_id,
      trigger_event_id: "trigger-evt",
      duration: 45,
      unit: "días",
      day_type: "corridos",
      calculated_date: null,
      calculation_status: "pending",
      deleted: false,
      created_at: "2026-08-28T12:00:00Z",
      updated_at: "2026-08-28T12:00:00Z",
    };
    const triggerEvent = createMockEvent({
      event_id: "trigger-evt",
      name: "Adjudicación",
      event_date: "2026-09-10",
    });

    render(<EventCard event={event} deadline={deadline} triggerEvent={triggerEvent} />);

    expect(screen.getByText("Entrega equipamiento")).toBeInTheDocument();
    expect(screen.getByText(/45 días corridos desde Adjudicación/)).toBeInTheDocument();
  });

  test("does not show dependency indicator when no deadline provided", () => {
    const event = createMockEvent({ name: "Evento sin dependencia" });

    render(<EventCard event={event} />);

    expect(screen.getByText("Evento sin dependencia")).toBeInTheDocument();
    expect(screen.queryByText(/días/)).not.toBeInTheDocument();
  });

  test("shows error indicator when deadline has calculation error", () => {
    const event = createMockEvent({ name: "Evento con error" });
    const deadline: Deadline = {
      id: "deadline-error",
      deadline_id: "deadline-error",
      analysis_id: "analysis-456",
      target_event_id: event.event_id,
      trigger_event_id: "trigger-evt",
      duration: 30,
      unit: "días",
      day_type: "corridos",
      calculated_date: null,
      calculation_status: "error",
      calculation_error: "Tipo de día no especificado en documento fuente",
      deleted: false,
      created_at: "2026-08-28T12:00:00Z",
      updated_at: "2026-08-28T12:00:00Z",
    };

    render(<EventCard event={event} deadline={deadline} />);

    expect(screen.getByText("Evento con error")).toBeInTheDocument();
    expect(screen.getByText("No se pudo calcular:")).toBeInTheDocument();
    expect(screen.getByText(/Tipo de día no especificado/)).toBeInTheDocument();
  });

  test("does not show dependency indicator when there is calculation error", () => {
    const event = createMockEvent({ name: "Evento con error" });
    const deadline: Deadline = {
      id: "deadline-error",
      deadline_id: "deadline-error",
      analysis_id: "analysis-456",
      target_event_id: event.event_id,
      trigger_event_id: "trigger-evt",
      duration: 30,
      unit: "días",
      day_type: "corridos",
      calculated_date: null,
      calculation_status: "error",
      calculation_error: "Error de cálculo",
      deleted: false,
      created_at: "2026-08-28T12:00:00Z",
      updated_at: "2026-08-28T12:00:00Z",
    };
    const triggerEvent = createMockEvent({
      event_id: "trigger-evt",
      name: "Trigger",
      event_date: "2026-09-10",
    });

    render(<EventCard event={event} deadline={deadline} triggerEvent={triggerEvent} />);

    // Debería mostrar error, no dependencia
    expect(screen.getByText("No se pudo calcular:")).toBeInTheDocument();
    expect(screen.queryByText(/días corridos desde/)).not.toBeInTheDocument();
  });
});
