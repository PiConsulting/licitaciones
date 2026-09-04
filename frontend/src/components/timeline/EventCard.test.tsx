import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EventCard, ConfirmedEvent } from "./EventCard";
import { Deadline } from "../../types/timeline";
import { ToastProvider } from "../ToastContainer";
import * as timelineApi from "../../api/timeline";

// Mock del API: EventCard solo llama directamente a setEventHidden (el
// resto de las mutaciones -- editar fecha, borrar -- viven en los modales
// que abre, que no se montan salvo que se les haga click).
vi.mock("../../api/timeline", () => ({
  setEventHidden: vi.fn(),
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
};

const ANALYSIS_ID = "analysis-456";

const createMockEvent = (overrides?: Partial<ConfirmedEvent>): ConfirmedEvent => ({
  id: "evt-123",
  event_id: "evt-123",
  analysis_id: ANALYSIS_ID,
  name: "Apertura de ofertas",
  event_date: "2026-09-15", // Siempre string (ConfirmedEvent)
  date_source: "detected",
  status: "confirmed",
  deleted: false,
  hidden: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

describe("EventCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders event with detected date", () => {
    const event = createMockEvent({
      name: "Adjudicación",
      event_date: "2026-09-10",
      date_source: "detected",
    });

    render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

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

    render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

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

    render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

    expect(screen.getByText("Cierre de consultas")).toBeInTheDocument();
    expect(screen.getByText("05/09/2026")).toBeInTheDocument();
    expect(screen.getByText("Calculada")).toBeInTheDocument();
  });

  test("calls onClick when card is clicked", async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();
    const event = createMockEvent();

    render(<EventCard analysisId={ANALYSIS_ID} event={event} onClick={handleClick} />, {
      wrapper: createWrapper(),
    });

    const card = screen.getByText("Apertura de ofertas").closest(".event-card");
    if (!card) throw new Error("Card not found");

    await user.click(card);

    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  test("has correct styling and structure", () => {
    const event = createMockEvent();

    render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

    const card = screen.getByText("Apertura de ofertas").closest(".event-card");
    expect(card).toHaveClass("rounded-lg", "border", "cursor-pointer");
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

    render(
      <EventCard analysisId={ANALYSIS_ID} event={event} deadline={deadline} triggerEvent={triggerEvent} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText("Entrega equipamiento")).toBeInTheDocument();
    expect(screen.getByText(/45 días corridos desde Adjudicación/)).toBeInTheDocument();
  });

  test("clicking deadline detail opens only deadline modal (no event modal)", async () => {
    const user = userEvent.setup();
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

    render(
      <EventCard analysisId={ANALYSIS_ID} event={event} deadline={deadline} triggerEvent={triggerEvent} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole("button", { name: /45 días corridos desde adjudicación/i }));

    expect(screen.getByText("Detalle del plazo")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar fecha" })).not.toBeInTheDocument();
  });

  test("does not show dependency indicator when no deadline provided", () => {
    const event = createMockEvent({ name: "Evento sin dependencia" });

    render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

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

    render(<EventCard analysisId={ANALYSIS_ID} event={event} deadline={deadline} />, {
      wrapper: createWrapper(),
    });

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

    render(
      <EventCard analysisId={ANALYSIS_ID} event={event} deadline={deadline} triggerEvent={triggerEvent} />,
      { wrapper: createWrapper() }
    );

    // Debería mostrar error, no dependencia
    expect(screen.getByText("No se pudo calcular:")).toBeInTheDocument();
    expect(screen.queryByText(/días corridos desde/)).not.toBeInTheDocument();
  });

  describe("ocultar/mostrar evento (2026-09-01)", () => {
    test("shows 'Ocultar' button when event is visible", () => {
      const event = createMockEvent();

      render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

      expect(screen.getByRole("button", { name: `Ocultar evento ${event.name}` })).toBeInTheDocument();
      expect(screen.queryByText("Oculto")).not.toBeInTheDocument();
    });

    test("shows 'Oculto' badge and 'Mostrar' button when event is hidden", () => {
      const event = createMockEvent({ hidden: true });

      render(<EventCard analysisId={ANALYSIS_ID} event={event} />, { wrapper: createWrapper() });

      expect(screen.getByText("Oculto")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: `Mostrar evento ${event.name}` })).toBeInTheDocument();
    });

    test("clicking 'Ocultar' calls setEventHidden with hidden=true and does not trigger onClick", async () => {
      const user = userEvent.setup();
      const handleClick = vi.fn();
      const mockSetEventHidden = vi.mocked(timelineApi.setEventHidden);
      mockSetEventHidden.mockResolvedValueOnce(createMockEvent({ hidden: true }));
      const event = createMockEvent();

      render(<EventCard analysisId={ANALYSIS_ID} event={event} onClick={handleClick} />, {
        wrapper: createWrapper(),
      });

      await user.click(screen.getByRole("button", { name: `Ocultar evento ${event.name}` }));

      expect(mockSetEventHidden).toHaveBeenCalledWith(ANALYSIS_ID, event.event_id, true);
      expect(handleClick).not.toHaveBeenCalled();
    });
  });
});
