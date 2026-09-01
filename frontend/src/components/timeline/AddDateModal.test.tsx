import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../ToastContainer";
import { AddDateModal } from "./AddDateModal";
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

describe("AddDateModal", () => {
  const mockOnClose = vi.fn();
  const pendingEvent: EventResponse = {
    id: "evt-1",
    event_id: "evt-1",
    analysis_id: "analysis-123",
    name: "Adjudicación",
    event_date: null,
    date_source: "pending",
    status: "pending",
    deleted: false,
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-08-31T12:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("AC1: debe renderizar modal con date picker", () => {
    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/Agregar fecha a "Adjudicación"/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Guardar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cancelar/i })).toBeInTheDocument();
  });

  test("debe mostrar texto explicativo sobre recálculo automático", () => {
    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(
      screen.getByText(/se calcularán automáticamente los eventos que dependen/i)
    ).toBeInTheDocument();
  });

  test("AC2: debe actualizar evento y recalcular dependencias", async () => {
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({
      ...pendingEvent,
      event_date: "2026-09-10",
      date_source: "user_input",
    });

    mockRecalc.mockResolvedValueOnce({
      events_updated: 2,
      errors: [],
    });

    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    // Seleccionar fecha
    const dateInput = screen.getByLabelText(/Fecha/i);
    fireEvent.change(dateInput, { target: { value: "2026-09-10" } });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    // Verificar llamadas a la API
    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith(
        "analysis-123",
        "evt-1",
        expect.objectContaining({
          event_date: "2026-09-10",
          date_source: "user_input",
        })
      );
      expect(mockRecalc).toHaveBeenCalledWith("analysis-123", "evt-1");
    });

    // Verificar que se cerró el modal
    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  test("AC2: debe mostrar toast con cantidad de eventos recalculados", async () => {
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({
      ...pendingEvent,
      event_date: "2026-09-10",
      date_source: "user_input",
    });

    mockRecalc.mockResolvedValueOnce({
      events_updated: 3,
      errors: [],
    });

    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(screen.getByText(/3 eventos dependientes/i)).toBeInTheDocument();
    });
  });

  test("debe mostrar mensaje simple si no hay eventos dependientes", async () => {
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({
      ...pendingEvent,
      event_date: "2026-09-10",
      date_source: "user_input",
    });

    mockRecalc.mockResolvedValueOnce({
      events_updated: 0,
      errors: [],
    });

    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(screen.getByText("Fecha agregada correctamente")).toBeInTheDocument();
    });
  });

  test("debe validar que la fecha es obligatoria", async () => {
    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    // Intentar submit sin fecha
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(screen.getByText("Debe seleccionar una fecha")).toBeInTheDocument();
    });

    expect(timelineApi.updateEvent).not.toHaveBeenCalled();
  });

  test("debe cerrar modal al hacer clic en Cancelar", () => {
    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/i }));

    expect(mockOnClose).toHaveBeenCalled();
    expect(timelineApi.updateEvent).not.toHaveBeenCalled();
  });

  test("debe invalidar queries después de actualizar", async () => {
    const mockUpdate = vi.mocked(timelineApi.updateEvent);
    const mockRecalc = vi.mocked(timelineApi.recalculateDependentDates);

    mockUpdate.mockResolvedValueOnce({
      ...pendingEvent,
      event_date: "2026-09-10",
      date_source: "user_input",
    });

    mockRecalc.mockResolvedValueOnce({
      events_updated: 1,
      errors: [],
    });

    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["timeline", "analysis-123"],
      });
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["timeline-deadlines", "analysis-123"],
      });
    });
  });

  test("debe mostrar error si falla la actualización", async () => {
    const mockUpdate = vi.mocked(timelineApi.updateEvent);

    mockUpdate.mockRejectedValueOnce(new Error("Error de red"));

    render(
      <AddDateModal event={pendingEvent} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Fecha/i), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Error/i)).toBeInTheDocument();
    });
  });
});
