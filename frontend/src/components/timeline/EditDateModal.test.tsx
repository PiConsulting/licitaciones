import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../ToastContainer";
import { EditDateModal } from "./EditDateModal";
import * as timelineApi from "../../api/timeline";
import type { EventResponse } from "../../types/timeline";

// Mock del API
vi.mock("../../api/timeline", () => ({
  updateEvent: vi.fn(),
  recalculateDependentDates: vi.fn(),
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
      <ToastProvider>
        {children}
      </ToastProvider>
    </QueryClientProvider>
  );
};

describe("EditDateModal", () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const createEvent = (overrides: Partial<EventResponse> = {}): EventResponse => ({
    id: "evt-1",
    event_id: "evt-1",
    analysis_id: "analysis-123",
    name: "Adjudicación",
    event_date: "2026-09-10",
    date_source: "detected",
    status: "confirmed",
    deleted: false,
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-08-31T12:00:00Z",
    ...overrides,
  });

  test("AC1: debe renderizar modal con fecha actual pre-seleccionada", () => {
    const event = createEvent({ event_date: "2026-09-10" });
    
    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/Editar fecha de "Adjudicación"/i)).toBeInTheDocument();
    const dateInput = screen.getByLabelText(/Fecha/i) as HTMLInputElement;
    expect(dateInput.value).toBe("2026-09-10");
  });

  test("AC2: debe actualizar fecha y cambiar date_source a user_input", async () => {
    const event = createEvent({ date_source: "detected" });
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({
      ...event,
      event_date: "2026-09-12",
      date_source: "user_input",
    });

    mockRecalc.mockResolvedValueOnce({
      events_updated: 1,
      errors: [],
    });

    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    // Cambiar fecha
    const dateInput = screen.getByLabelText(/Fecha/i);
    fireEvent.change(dateInput, { target: { value: "2026-09-12" } });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /Actualizar/i }));

    // Verificar llamadas
    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        "analysis-123",
        "evt-1",
        expect.objectContaining({
          event_date: "2026-09-12",
          date_source: "user_input", // Cambia a user_input siempre
        })
      );
      expect(mockRecalc).toHaveBeenCalledWith("analysis-123", "evt-1");
    });
  });

  test("AC3: debe mostrar advertencia para fechas calculadas", () => {
    const event = createEvent({ date_source: "calculated" });
    
    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/se calculó automáticamente/i)).toBeInTheDocument();
    expect(screen.getByText(/futuros recálculos no la sobrescribirán/i)).toBeInTheDocument();
  });

  test("NO debe mostrar advertencia para fechas detectadas o user_input", () => {
    const eventDetected = createEvent({ date_source: "detected" });
    
    const { rerender } = render(
      <EditDateModal event={eventDetected} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByText(/se calculó automáticamente/i)).not.toBeInTheDocument();

    // Rerender con user_input
    const eventUserInput = createEvent({ date_source: "user_input" });
    rerender(
      <EditDateModal event={eventUserInput} open={true} onClose={mockOnClose} />
    );

    expect(screen.queryByText(/se calculó automáticamente/i)).not.toBeInTheDocument();
  });

  test("debe mostrar toast con eventos recalculados", async () => {
    const { toast } = await import("../../components/Toast");
    const event = createEvent();
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({ ...event, date_source: "user_input" });
    mockRecalc.mockResolvedValueOnce({
      events_updated: 3,
      errors: [],
    });

    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-15" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Actualizar/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining("3 eventos dependientes")
      );
    });
  });

  test("debe validar que la fecha es obligatoria", async () => {
    const event = createEvent();
    
    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    // Limpiar fecha
    const dateInput = screen.getByLabelText(/Fecha/i);
    fireEvent.change(dateInput, { target: { value: "" } });

    // Intentar submit
    fireEvent.click(screen.getByRole("button", { name: /Actualizar/i }));

    await waitFor(() => {
      expect(screen.getByText("Debe seleccionar una fecha")).toBeInTheDocument();
    });

    expect(timelineApi.updateEvent).not.toHaveBeenCalled();
  });

  test("debe cerrar modal al hacer clic en Cancelar", () => {
    const event = createEvent();
    
    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/i }));

    expect(mockOnClose).toHaveBeenCalled();
    expect(timelineApi.updateEvent).not.toHaveBeenCalled();
  });

  test("debe cerrar modal después de actualizar exitosamente", async () => {
    const event = createEvent();
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({ ...event, date_source: "user_input" });
    mockRecalc.mockResolvedValueOnce({ events_updated: 0, errors: [] });

    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-20" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Actualizar/i }));

    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  test("debe mostrar error si falla la actualización", async () => {
    const event = createEvent();
    const mockUpdate = vi.mocked(timelineApi.updateEvent);

    mockUpdate.mockRejectedValueOnce(new Error("Error de red"));

    render(
      <EditDateModal event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-20" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Actualizar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Error/i)).toBeInTheDocument();
    });
  });
});
