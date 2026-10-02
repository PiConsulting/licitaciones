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

    const button = screen.getByText(/45 días corridos/).closest("button");
    expect(button).toHaveClass("text-[rgba(0,60,107,.68)]");
  });

  test("has correct styling for pending dependency", () => {
    const deadline = createMockDeadline();
    const triggerEvent = createMockTriggerEvent({ event_date: null });

    render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />);

    const button = screen.getByText(/Pendiente de fecha/).closest("button");
    expect(button).toHaveClass("text-[rgba(0,60,107,.68)]");
  });

  describe("target con fecha propia independiente del disparador (2026-10-02)", () => {
    // Bug real (Corrientes): "Presentación de la Oferta" ya tenía su propia fecha
    // DETECTADA en el pliego (05/08/2026), pero una extracción separada del mismo
    // hito real como plazo relativo ("Fecha de Tope de Presentación de Ofertas"
    // como disparador, sin fecha propia) hacía que la card mostrara "Pendiente de
    // fecha de Fecha de Tope..." -- falso, la fecha del evento no depende de ESE
    // plazo en absoluto.
    const createMockTargetEvent = (overrides?: Partial<Event>): Event => ({
      id: "event-target",
      event_id: "event-target",
      analysis_id: "analysis-456",
      name: "Presentación de la Oferta",
      event_date: "2026-08-05",
      date_source: "detected",
      status: "confirmed",
      deleted: false,
      created_at: "2026-08-28T12:00:00Z",
      updated_at: "2026-08-28T12:00:00Z",
      ...overrides,
    });

    test("no muestra nada si el target ya tiene fecha detectada y el disparador no tiene fecha", () => {
      const deadline = createMockDeadline();
      const triggerEvent = createMockTriggerEvent({
        name: "Fecha de Tope de Presentación de Ofertas",
        event_date: null,
      });
      const targetEvent = createMockTargetEvent();

      const { container } = render(
        <DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} targetEvent={targetEvent} />
      );

      expect(screen.queryByText(/Pendiente de fecha/)).not.toBeInTheDocument();
      expect(container).toBeEmptyDOMElement();
    });

    test("no muestra nada si el target tiene fecha ingresada a mano (user_input) y el disparador no tiene fecha", () => {
      const deadline = createMockDeadline();
      const triggerEvent = createMockTriggerEvent({ event_date: null });
      const targetEvent = createMockTargetEvent({ date_source: "user_input" });

      const { container } = render(
        <DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} targetEvent={targetEvent} />
      );

      expect(container).toBeEmptyDOMElement();
    });

    test("SÍ muestra 'Pendiente de fecha' si el target no tiene fecha propia todavía", () => {
      const deadline = createMockDeadline();
      const triggerEvent = createMockTriggerEvent({ event_date: null });
      const targetEvent = createMockTargetEvent({ event_date: null, date_source: "pending" });

      render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} targetEvent={targetEvent} />);

      expect(screen.getByText(/Pendiente de fecha/)).toBeInTheDocument();
    });

    test("SÍ muestra 'Pendiente de fecha' si la fecha del target vino calculada de este mismo plazo", () => {
      const deadline = createMockDeadline();
      const triggerEvent = createMockTriggerEvent({ event_date: null });
      const targetEvent = createMockTargetEvent({ date_source: "calculated" });

      render(<DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} targetEvent={targetEvent} />);

      expect(screen.getByText(/Pendiente de fecha/)).toBeInTheDocument();
    });
  });
});
