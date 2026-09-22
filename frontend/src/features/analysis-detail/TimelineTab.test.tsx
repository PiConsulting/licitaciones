import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TimelineTab } from "./TimelineTab";
import { ToastProvider } from "../../components/ToastContainer";
import * as timelineApi from "../../api/timeline";
import type { Event, Deadline } from "../../types/timeline";

vi.mock("../../api/timeline");

const mockGetTimelineEvents = vi.mocked(timelineApi.getTimelineEvents);
const mockGetTimelineDeadlines = vi.mocked(timelineApi.getTimelineDeadlines);

// ToastProvider es necesario porque EventCard/PendingEventCard/AnchorDatesPanel usan useToast(), que tira sin el provider.
function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  );
}

describe("TimelineTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTimelineEvents.mockResolvedValue([]);
    mockGetTimelineDeadlines.mockResolvedValue([]);
  });

  test("renders timeline tab with header", async () => {
    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText(/Eventos y plazos del proceso de licitación/)).toBeInTheDocument();
    
    await waitFor(() => {
      // Siempre se pide con includeHidden para poder togglear "Mostrar ocultos" sin un segundo fetch; el filtrado real es del lado del cliente.
      expect(mockGetTimelineEvents).toHaveBeenCalledWith("analysis-123", { includeHidden: true });
    });
  });

  test("shows add event button", async () => {
    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    const button = screen.getByRole("button", { name: /Agregar evento/i });
    expect(button).toBeInTheDocument();
  });

  test("shows loading state", () => {
    mockGetTimelineEvents.mockImplementation(() => new Promise(() => {}));
    mockGetTimelineDeadlines.mockImplementation(() => new Promise(() => {}));

    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    expect(screen.getByText(/Cargando eventos/)).toBeInTheDocument();
  });

  test("shows empty state when no events", async () => {
    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    await waitFor(() => {
      expect(screen.getByText("No se encontraron eventos temporales")).toBeInTheDocument();
    });
  });

  test("shows error state on API failure", async () => {
    mockGetTimelineEvents.mockRejectedValue(new Error("Network error"));

    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    await waitFor(() => {
      expect(screen.getByText(/Error al cargar eventos/)).toBeInTheDocument();
    });
  });

  describe("ocultar/mostrar eventos (2026-09-01)", () => {
    const makeEvent = (overrides: Partial<Event>): Event => ({
      id: `event::${overrides.event_id}`,
      event_id: "evt-1",
      analysis_id: "analysis-123",
      name: "Evento",
      event_date: "2026-09-10",
      date_source: "detected",
      status: "confirmed",
      deleted: false,
      hidden: false,
      created_at: "2026-08-28T12:00:00Z",
      updated_at: "2026-08-28T12:00:00Z",
      ...overrides,
    });

    test("hidden events do not count in stats and are not shown by default", async () => {
      mockGetTimelineEvents.mockResolvedValue([
        makeEvent({ event_id: "evt-visible", name: "Apertura de ofertas" }),
        makeEvent({ event_id: "evt-hidden", name: "Notificación de fuerza mayor", hidden: true }),
      ]);

      renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

      await waitFor(() => {
        expect(screen.getByText("Apertura de ofertas")).toBeInTheDocument();
      });

      expect(screen.queryByText("Notificación de fuerza mayor")).not.toBeInTheDocument();
      // Stats: 1 de 1 (el oculto no cuenta)
      expect(screen.getByText(/1 de 1 eventos con fecha confirmada/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Mostrar ocultos \(1\)/i })).toBeInTheDocument();
    });

    test("toggling 'Mostrar ocultos' reveals the hidden event without changing stats", async () => {
      const user = userEvent.setup();
      mockGetTimelineEvents.mockResolvedValue([
        makeEvent({ event_id: "evt-visible", name: "Apertura de ofertas" }),
        makeEvent({ event_id: "evt-hidden", name: "Notificación de fuerza mayor", hidden: true }),
      ]);

      renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

      await waitFor(() => {
        expect(screen.getByText("Apertura de ofertas")).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /Mostrar ocultos \(1\)/i }));

      expect(screen.getByText("Notificación de fuerza mayor")).toBeInTheDocument();
      // Stats no cambian por el toggle
      expect(screen.getByText(/1 de 1 eventos con fecha confirmada/)).toBeInTheDocument();
    });
  });

  describe("vista de línea de tiempo (2026-09-01)", () => {
    const makeEvent = (overrides: Partial<Event>): Event => ({
      id: `event::${overrides.event_id}`,
      event_id: "evt-1",
      analysis_id: "analysis-123",
      name: "Evento",
      event_date: "2026-09-10",
      date_source: "detected",
      status: "confirmed",
      deleted: false,
      hidden: false,
      created_at: "2026-08-28T12:00:00Z",
      updated_at: "2026-08-28T12:00:00Z",
      ...overrides,
    });

    test("por default se ve la lista; el toggle cambia a la línea de tiempo con HOY marcado", async () => {
      const user = userEvent.setup();
      mockGetTimelineEvents.mockResolvedValue([
        makeEvent({ event_id: "evt-1", name: "Apertura de ofertas", event_date: "2026-09-10" }),
      ]);

      renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

      await waitFor(() => {
        expect(screen.getByText("Apertura de ofertas")).toBeInTheDocument();
      });

      // En la lista, EventCard trae botón de "Editar fecha" -- en la línea de tiempo (solo lectura) no debería estar.
      expect(screen.getByRole("button", { name: /Editar fecha de Apertura de ofertas/i })).toBeInTheDocument();
      expect(screen.queryByText(/^HOY/)).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /Línea de tiempo/i }));

      expect(screen.getByText(/^HOY/)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Editar fecha de Apertura de ofertas/i })
      ).not.toBeInTheDocument();
      // El evento se sigue viendo, ahora como punto clickeable en la línea.
      expect(screen.getByRole("button", { name: /Apertura de ofertas/i })).toBeInTheDocument();
    });

    test("la línea de tiempo no muestra fechas ancla ni eventos pendientes, solo los confirmados", async () => {
      const user = userEvent.setup();
      mockGetTimelineEvents.mockResolvedValue([
        makeEvent({ event_id: "evt-confirmed", name: "Apertura de ofertas", event_date: "2026-09-10" }),
        makeEvent({
          event_id: "evt-anchor",
          name: "Adjudicación",
          event_date: null,
        }),
      ]);
      mockGetTimelineDeadlines.mockResolvedValue([
        {
          id: "deadline::dl-1",
          deadline_id: "dl-1",
          analysis_id: "analysis-123",
          target_event_id: "evt-pending-other",
          trigger_event_id: "evt-anchor",
          duration: 10,
          day_type: "hábiles",
          deleted: false,
          created_at: "2026-08-28T12:00:00Z",
          updated_at: "2026-08-28T12:00:00Z",
        } as Deadline,
      ]);

      renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

      await waitFor(() => {
        expect(screen.getByText("Apertura de ofertas")).toBeInTheDocument();
      });

      // En la lista se ve el panel de fechas ancla.
      expect(screen.getByText("Adjudicación")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /Línea de tiempo/i }));

      // En línea de tiempo, solo el evento confirmado -- nada de anclas/pendientes.
      expect(screen.getByText("Apertura de ofertas")).toBeInTheDocument();
      expect(screen.queryByText("Adjudicación")).not.toBeInTheDocument();
      expect(screen.queryByText(/Eventos Pendientes/i)).not.toBeInTheDocument();
    });
  });
});
