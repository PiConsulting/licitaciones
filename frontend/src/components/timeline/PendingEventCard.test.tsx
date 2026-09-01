import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PendingEventCard } from "./PendingEventCard";
import { Event, DeadlineResponse } from "../../types/timeline";
import { ToastProvider } from "../ToastContainer";
import * as timelineApi from "../../api/timeline";

// Mock del API: PendingEventCard solo llama directamente a setEventHidden.
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

const createMockPendingEvent = (overrides?: Partial<Event>): Event => ({
  id: "evt-pending-123",
  event_id: "evt-pending-123",
  analysis_id: ANALYSIS_ID,
  name: "Adjudicación",
  event_date: null,
  date_source: "pending",
  status: "pending",
  deleted: false,
  hidden: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

const createMockDeadline = (overrides?: Partial<DeadlineResponse>): DeadlineResponse => ({
  id: "deadline-1",
  deadline_id: "deadline-1",
  analysis_id: ANALYSIS_ID,
  name: "Plazo",
  trigger_event_id: "trigger-evt",
  target_event_id: "evt-pending-123",
  duration: 45,
  unit: "días",
  day_type: "corridos",
  es_plazo_maximo: false,
  deadline_date: null,
  calculation_status: "pending",
  deleted: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

describe("PendingEventCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders pending event with name", () => {
    const event = createMockPendingEvent({ name: "Entrega de equipamiento" });
    const handleAddDate = vi.fn();

    render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText("Entrega de equipamiento")).toBeInTheDocument();
    expect(screen.getByText("Fecha pendiente")).toBeInTheDocument();
  });

  test("shows pendiente badge", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText("Pendiente")).toBeInTheDocument();
  });

  test("shows add date button", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
      wrapper: createWrapper(),
    });

    const button = screen.getByRole("button", { name: /Agregar fecha/i });
    expect(button).toBeInTheDocument();
  });

  test("calls onAddDate when button is clicked", async () => {
    const user = userEvent.setup();
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
      wrapper: createWrapper(),
    });

    const button = screen.getByRole("button", { name: /Agregar fecha/i });
    await user.click(button);

    expect(handleAddDate).toHaveBeenCalledTimes(1);
  });

  test("shows dependents warning when hasDependents is true", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(
      <PendingEventCard analysisId={ANALYSIS_ID} event={event} hasDependents={true} onAddDate={handleAddDate} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText("Otros eventos dependen de esta fecha")).toBeInTheDocument();
  });

  test("does not show dependents warning when hasDependents is false", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(
      <PendingEventCard analysisId={ANALYSIS_ID} event={event} hasDependents={false} onAddDate={handleAddDate} />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByText("Otros eventos dependen de esta fecha")).not.toBeInTheDocument();
  });

  test("has correct styling with dashed border", () => {
    const event = createMockPendingEvent();
    const handleAddDate = vi.fn();

    render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
      wrapper: createWrapper(),
    });

    const card = screen.getByText("Adjudicación").closest(".pending-event-card");
    expect(card).toHaveClass("border-dashed", "border-gray-300", "bg-gray-50/50");
  });

  describe("ocultar/mostrar evento (2026-09-01)", () => {
    test("shows 'Ocultar' action when event is visible", () => {
      const event = createMockPendingEvent();
      const handleAddDate = vi.fn();

      render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole("button", { name: `Ocultar evento ${event.name}` })).toBeInTheDocument();
      expect(screen.queryByText("Oculto")).not.toBeInTheDocument();
    });

    test("shows 'Oculto' badge and 'Mostrar' action when event is hidden", () => {
      const event = createMockPendingEvent({ hidden: true });
      const handleAddDate = vi.fn();

      render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText("Oculto")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: `Mostrar evento ${event.name}` })).toBeInTheDocument();
    });

    test("clicking 'Ocultar' calls setEventHidden with hidden=true", async () => {
      const user = userEvent.setup();
      const mockSetEventHidden = vi.mocked(timelineApi.setEventHidden);
      mockSetEventHidden.mockResolvedValueOnce(createMockPendingEvent({ hidden: true }));
      const event = createMockPendingEvent();
      const handleAddDate = vi.fn();

      render(<PendingEventCard analysisId={ANALYSIS_ID} event={event} onAddDate={handleAddDate} />, {
        wrapper: createWrapper(),
      });

      await user.click(screen.getByRole("button", { name: `Ocultar evento ${event.name}` }));

      expect(mockSetEventHidden).toHaveBeenCalledWith(ANALYSIS_ID, event.event_id, true);
    });
  });

  describe("tipo de día no especificado (2026-09-01)", () => {
    test("avisa que hay que cargar la fecha a mano cuando day_type es no_especificado", () => {
      const event = createMockPendingEvent({ name: "Entrega de equipamiento" });
      const deadline = createMockDeadline({ day_type: "no_especificado" });
      const triggerEvent = createMockPendingEvent({ event_id: "trigger-evt", name: "Adjudicación" });
      const handleAddDate = vi.fn();

      render(
        <PendingEventCard
          analysisId={ANALYSIS_ID}
          event={event}
          deadline={deadline}
          triggerEvent={triggerEvent}
          onAddDate={handleAddDate}
        />,
        { wrapper: createWrapper() }
      );

      expect(
        screen.getByText(/El pliego no especifica si son días hábiles o corridos/)
      ).toBeInTheDocument();
      expect(screen.queryByText(/^Se calcula:/)).not.toBeInTheDocument();
    });

    test("no muestra el aviso cuando day_type sí está especificado", () => {
      const event = createMockPendingEvent({ name: "Entrega de equipamiento" });
      const deadline = createMockDeadline({ day_type: "corridos" });
      const triggerEvent = createMockPendingEvent({ event_id: "trigger-evt", name: "Adjudicación" });
      const handleAddDate = vi.fn();

      render(
        <PendingEventCard
          analysisId={ANALYSIS_ID}
          event={event}
          deadline={deadline}
          triggerEvent={triggerEvent}
          onAddDate={handleAddDate}
        />,
        { wrapper: createWrapper() }
      );

      expect(
        screen.queryByText(/El pliego no especifica si son días hábiles o corridos/)
      ).not.toBeInTheDocument();
      expect(screen.getByText(/Se calcula: 45 días corridos desde/)).toBeInTheDocument();
    });

    test("muestra el error de cálculo cuando calculation_status es error", () => {
      const event = createMockPendingEvent({ name: "Entrega de equipamiento" });
      const deadline = createMockDeadline({
        day_type: "corridos",
        calculation_status: "error",
        calculation_error: "Ciclo de dependencia detectado",
      });
      const handleAddDate = vi.fn();

      render(
        <PendingEventCard
          analysisId={ANALYSIS_ID}
          event={event}
          deadline={deadline}
          onAddDate={handleAddDate}
        />,
        { wrapper: createWrapper() }
      );

      expect(screen.getByText(/Ciclo de dependencia detectado/)).toBeInTheDocument();
    });
  });
});
