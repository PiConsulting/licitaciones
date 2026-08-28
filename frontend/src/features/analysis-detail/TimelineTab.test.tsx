import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TimelineTab } from "./TimelineTab";
import * as timelineApi from "../../api/timeline";
import type { Event, Deadline } from "../../types/timeline";

// Mock de las APIs
vi.mock("../../api/timeline");

const mockGetTimelineEvents = vi.mocked(timelineApi.getTimelineEvents);
const mockGetTimelineDeadlines = vi.mocked(timelineApi.getTimelineDeadlines);

// Helper para renderizar con QueryClient
function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe("TimelineTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: sin eventos
    mockGetTimelineEvents.mockResolvedValue([]);
    mockGetTimelineDeadlines.mockResolvedValue([]);
  });

  test("renders timeline tab with header", async () => {
    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    expect(screen.getByText("Timeline")).toBeInTheDocument();
    expect(screen.getByText(/Eventos y plazos del proceso de licitación/)).toBeInTheDocument();
    
    await waitFor(() => {
      expect(mockGetTimelineEvents).toHaveBeenCalledWith("analysis-123");
    });
  });

  test("shows add event button", async () => {
    renderWithQueryClient(<TimelineTab analysisId="analysis-123" />);

    const button = screen.getByRole("button", { name: /Agregar evento/i });
    expect(button).toBeInTheDocument();
  });

  test("shows loading state", () => {
    // Mock de queries que nunca resuelven para simular loading
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
});
