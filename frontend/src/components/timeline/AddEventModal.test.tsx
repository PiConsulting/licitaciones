import { describe, test, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../ToastContainer";
import { AddEventModal } from "./AddEventModal";
import * as timelineApi from "../../api/timeline";

vi.mock("../../api/timeline", () => ({
  createEvent: vi.fn(),
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

describe("AddEventModal", () => {
  const mockOnClose = vi.fn();
  const analysisId = "test-analysis-123";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("AC1: debe renderizar modal con todos los campos requeridos", () => {
    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText("Agregar evento")).toBeInTheDocument();

    expect(screen.getByLabelText(/Nombre del evento/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha \(opcional\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Observación \(opcional\)/i)).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Cancelar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Guardar/i })).toBeInTheDocument();
  });

  test("AC3: debe validar que el nombre del evento es obligatorio", async () => {
    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    const submitButton = screen.getByRole("button", { name: /Guardar/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(
        screen.getByText(/El nombre del evento es obligatorio/i)
      ).toBeInTheDocument();
    });

    expect(timelineApi.createEvent).not.toHaveBeenCalled();
  });

  test("AC2: debe crear evento exitosamente con nombre solamente", async () => {
    const mockCreateEvent = vi.mocked(timelineApi.createEvent);
    mockCreateEvent.mockResolvedValueOnce({
      id: "evt-1",
      event_id: "evt-1",
      analysis_id: analysisId,
      name: "Apertura de sobres",
      event_date: null,
      date_source: "pending",
      status: "confirmed",
      deleted: false,
      created_at: "2026-08-31T12:00:00Z",
      updated_at: "2026-08-31T12:00:00Z",
    });

    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    const nameInput = screen.getByLabelText(/Nombre del evento/i);
    fireEvent.change(nameInput, { target: { value: "Apertura de sobres" } });

    const submitButton = screen.getByRole("button", { name: /Guardar/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockCreateEvent).toHaveBeenCalledWith(analysisId, {
        name: "Apertura de sobres",
        event_date: null,
        date_source: "pending",
        status: "confirmed",
        source_fragment: undefined,
      });
    });

    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  test("debe crear evento con fecha cuando se proporciona", async () => {
    const mockCreateEvent = vi.mocked(timelineApi.createEvent);
    mockCreateEvent.mockResolvedValueOnce({
      id: "evt-2",
      event_id: "evt-2",
      analysis_id: analysisId,
      name: "Adjudicación",
      event_date: "2026-09-10",
      date_source: "user_input",
      status: "confirmed",
      deleted: false,
      created_at: "2026-08-31T12:00:00Z",
      updated_at: "2026-08-31T12:00:00Z",
    });

    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Nombre del evento/i), {
      target: { value: "Adjudicación" },
    });
    fireEvent.change(screen.getByLabelText(/Fecha \(opcional\)/i), {
      target: { value: "2026-09-10" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(mockCreateEvent).toHaveBeenCalledWith(analysisId, {
        name: "Adjudicación",
        event_date: "2026-09-10",
        date_source: "user_input",
        status: "confirmed",
        source_fragment: undefined,
      });
    });
  });

  test("debe crear evento con observación cuando se proporciona", async () => {
    const mockCreateEvent = vi.mocked(timelineApi.createEvent);
    mockCreateEvent.mockResolvedValueOnce({
      id: "evt-3",
      event_id: "evt-3",
      analysis_id: analysisId,
      name: "Firma de contrato",
      event_date: null,
      date_source: "pending",
      status: "confirmed",
      deleted: false,
      created_at: "2026-08-31T12:00:00Z",
      updated_at: "2026-08-31T12:00:00Z",
    });

    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Nombre del evento/i), {
      target: { value: "Firma de contrato" },
    });
    fireEvent.change(screen.getByLabelText(/Observación \(opcional\)/i), {
      target: { value: "Requiere presencia del representante legal" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(mockCreateEvent).toHaveBeenCalledWith(analysisId, {
        name: "Firma de contrato",
        event_date: null,
        date_source: "pending",
        status: "confirmed",
        source_fragment: "Requiere presencia del representante legal",
      });
    });
  });

  test("debe cerrar modal al hacer clic en Cancelar sin llamar a la API", () => {
    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    const cancelButton = screen.getByRole("button", { name: /Cancelar/i });
    fireEvent.click(cancelButton);

    expect(mockOnClose).toHaveBeenCalled();
    expect(timelineApi.createEvent).not.toHaveBeenCalled();
  });

  test("debe mostrar estado de carga durante el submit", async () => {
    let resolveCreate: any;
    const mockCreateEvent = vi.mocked(timelineApi.createEvent);
    mockCreateEvent.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        })
    );

    render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Nombre del evento/i), {
      target: { value: "Test Event" },
    });

    const submitButton = screen.getByRole("button", { name: /Guardar/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(submitButton).toBeDisabled();
    });

    resolveCreate({
      id: "evt-4",
      event_id: "evt-4",
      analysis_id: analysisId,
      name: "Test",
      event_date: null,
      date_source: "pending",
      status: "confirmed",
      deleted: false,
      created_at: "2026-08-31T12:00:00Z",
      updated_at: "2026-08-31T12:00:00Z",
    });
  });

  test("debe limpiar el formulario después de crear evento exitosamente", async () => {
    const mockCreateEvent = vi.mocked(timelineApi.createEvent);
    mockCreateEvent.mockResolvedValueOnce({
      id: "evt-5",
      event_id: "evt-5",
      analysis_id: analysisId,
      name: "Evento Test",
      event_date: null,
      date_source: "pending",
      status: "confirmed",
      deleted: false,
      created_at: "2026-08-31T12:00:00Z",
      updated_at: "2026-08-31T12:00:00Z",
    });

    const { rerender } = render(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />,
      { wrapper: createWrapper() }
    );

    fireEvent.change(screen.getByLabelText(/Nombre del evento/i), {
      target: { value: "Evento Test" },
    });
    fireEvent.change(screen.getByLabelText(/Fecha \(opcional\)/i), {
      target: { value: "2026-09-15" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));

    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
    });

    mockOnClose.mockClear();
    rerender(
      <AddEventModal analysisId={analysisId} open={true} onClose={mockOnClose} />
    );

    expect(screen.getByLabelText(/Nombre del evento/i)).toHaveValue("");
    expect(screen.getByLabelText(/Fecha \(opcional\)/i)).toHaveValue("");
  });
});
