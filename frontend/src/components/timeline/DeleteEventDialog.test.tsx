import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../ToastContainer";
import { DeleteEventDialog } from "./DeleteEventDialog";
import * as timelineApi from "../../api/timeline";
import type { EventResponse } from "../../types/timeline";

// Mock del API
vi.mock("../../api/timeline", () => ({
  deleteEvent: vi.fn(),
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

describe("DeleteEventDialog", () => {
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
    date_source: "user_input",
    status: "confirmed",
    deleted: false,
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-08-31T12:00:00Z",
    ...overrides,
  });

  test("AC1: debe mostrar confirmación con advertencia de dependencias", () => {
    const event = createEvent();
    
    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/¿Eliminar "Adjudicación"\?/i)).toBeInTheDocument();
    expect(screen.getByText(/plazos que dependan de este evento quedarán pendientes/i)).toBeInTheDocument();
  });

  test("AC2: debe ejecutar soft delete al confirmar", async () => {
    const event = createEvent();
    const mockDelete = vi.mocked(timelineApi.deleteEvent);
    mockDelete.mockResolvedValueOnce(undefined);

    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Eliminar/i }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("analysis-123", "evt-1");
    });
  });

  test("AC3: debe mostrar advertencia adicional para eventos detectados", () => {
    const event = createEvent({ date_source: "detected" });
    
    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/detectado automáticamente/i)).toBeInTheDocument();
    expect(screen.getByText(/reaparecerá en el próximo análisis/i)).toBeInTheDocument();
  });

  test("NO debe mostrar advertencia de re-aparición para eventos creados por usuario", () => {
    const event = createEvent({ date_source: "user_input" });
    
    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByText(/detectado automáticamente/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reaparecerá/i)).not.toBeInTheDocument();
  });

  test("debe mostrar toast de éxito después de eliminar", async () => {
    const event = createEvent();
    const mockDelete = vi.mocked(timelineApi.deleteEvent);
    mockDelete.mockResolvedValueOnce(undefined);

    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Eliminar/i }));

    await waitFor(() => {
      expect(screen.getByText("Evento eliminado")).toBeInTheDocument();
    });
  });

  test("debe cerrar diálogo después de eliminar exitosamente", async () => {
    const event = createEvent();
    const mockDelete = vi.mocked(timelineApi.deleteEvent);
    mockDelete.mockResolvedValueOnce(undefined);

    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Eliminar/i }));

    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  test("debe cerrar diálogo al hacer clic en Cancelar", () => {
    const event = createEvent();
    
    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/i }));

    expect(mockOnClose).toHaveBeenCalled();
    expect(timelineApi.deleteEvent).not.toHaveBeenCalled();
  });

  test("debe mostrar error si falla la eliminación", async () => {
    const event = createEvent();
    const mockDelete = vi.mocked(timelineApi.deleteEvent);
    mockDelete.mockRejectedValueOnce(new Error("Error de red"));

    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole("button", { name: /Eliminar/i }));

    await waitFor(() => {
      expect(screen.getByText(/Error/i)).toBeInTheDocument();
    });

    expect(mockOnClose).not.toHaveBeenCalled();
  });

  test("debe deshabilitar botón Eliminar mientras se procesa", async () => {
    const event = createEvent();
    const mockDelete = vi.mocked(timelineApi.deleteEvent);
    mockDelete.mockImplementation(() => new Promise(() => {})); // Never resolves

    render(
      <DeleteEventDialog event={event} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    const deleteButton = screen.getByRole("button", { name: /Eliminar/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(deleteButton).toBeDisabled();
    });
  });
});
