import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "../components/ToastContainer";
import Dashboard from "./Dashboard";
import { startAnalysis } from "../api/analyses";
import { getUpcomingEvents } from "../api/upcomingEvents";
import { useAnalysisBusinessUnitsQuery } from "../features/analysis/hooks/useAnalysisBusinessUnitsQuery";
import { useAnalysesQuery } from "../features/analysis/hooks/useAnalysesQuery";
import { useAnalysisFilters } from "../features/analysis/hooks/useAnalysisFilters";

vi.mock("../features/analysis/hooks/useAnalysesQuery", () => ({
  useAnalysesQuery: vi.fn(),
}));

vi.mock("../features/analysis/hooks/useAnalysisBusinessUnitsQuery", () => ({
  useAnalysisBusinessUnitsQuery: vi.fn(),
}));

vi.mock("../api/analyses", () => ({
  startAnalysis: vi.fn(),
}));

vi.mock("../api/upcomingEvents", () => ({
  getUpcomingEvents: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Dashboard", () => {
  beforeEach(() => {
    vi.mocked(getUpcomingEvents).mockResolvedValue([]);
    vi.mocked(useAnalysisBusinessUnitsQuery).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysisBusinessUnitsQuery>);
  });

  test("muestra estado vacío con CTA al wizard", () => {
    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: { items: [], page: 1, per_page: 20, total: 0, total_pages: 1 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Todavía no hay análisis")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ir al wizard de upload/i })).toBeInTheDocument();
  });

  test("renderiza KPIs del Home con total real y estados neutros", () => {
    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: { items: [], page: 1, per_page: 20, total: 12, total_pages: 1 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("heading", { name: "Licitaciones" })).toBeInTheDocument();
    expect(screen.getByLabelText("Indicadores")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-total")).toHaveTextContent("12");
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
    expect(screen.getByTestId("kpi-no-aprobadas")).toHaveTextContent("0");
    expect(screen.getByTestId("kpi-en-revision")).toHaveTextContent("0");
    expect(screen.getByTestId("kpi-presentadas")).toHaveTextContent("0");
    expect(screen.getByTestId("kpi-ganadas")).toHaveTextContent("0");
    expect(screen.getByTestId("kpi-perdidas")).toHaveTextContent("0");
    expect(screen.queryByRole("heading", { name: /por vencer/i })).not.toBeInTheDocument();
  });

  test("muestra filtros de fecha migrados a pills y no renderiza unidad sin dato real", () => {
    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: { items: [], page: 1, per_page: 20, total: 1, total_pages: 1 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: "Todo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Últimos 30 días" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Este trimestre" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Personalizado" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Buscar por pliego u organismo")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filtro de unidad" })).not.toBeInTheDocument();
  });

  test("renderiza unidad CEDI cuando FE2 expone business_unit", () => {
    vi.mocked(useAnalysisBusinessUnitsQuery).mockReturnValue({
      data: [{ business_unit: "CEDI", count: 1 }],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysisBusinessUnitsQuery>);

    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: {
        items: [
          {
            id: "an-1",
            analysis_name: "Pliego 1",
            business_unit: "CEDI",
            status: "analyzed",
            current_stage: "completed",
            progress_percentage: 100,
            created_at: "2026-09-23T12:00:00Z",
          },
        ],
        page: 1,
        per_page: 20,
        total: 1,
        total_pages: 1,
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("group", { name: "Filtro de unidad" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CEDI\s*1/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("renderiza unidades dinámicas desde backend sin hardcode", () => {
    vi.mocked(useAnalysisBusinessUnitsQuery).mockReturnValue({
      data: [
        { business_unit: "CEDI", count: 3 },
        { business_unit: "Wemox", count: 2 },
      ],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysisBusinessUnitsQuery>);

    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: { items: [], page: 1, per_page: 20, total: 1, total_pages: 1 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: /CEDI\s*3/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Wemox\s*2/i })).toBeInTheDocument();
  });

  test("filtra análisis por unidad al clickear chip", () => {
    vi.mocked(useAnalysisBusinessUnitsQuery).mockReturnValue({
      data: [
        { business_unit: "CEDI", count: 3 },
        { business_unit: "PI", count: 2 },
      ],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysisBusinessUnitsQuery>);

    vi.mocked(useAnalysesQuery).mockImplementation(() => ({
      data: { items: [], page: 1, per_page: 20, total: 0, total_pages: 1 },
      isLoading: false,
      isError: false,
    }) as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /PI\s*2/i }));

    const calls = vi.mocked(useAnalysesQuery).mock.calls;
    const latestFilters = calls.at(-1)?.[0];
    expect(latestFilters?.business_unit).toBe("PI");
  });

  test("kpis clickeables filtran la lista por estado de negocio", () => {
    vi.mocked(useAnalysisBusinessUnitsQuery).mockReturnValue({
      data: [{ business_unit: "CEDI", count: 2 }],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysisBusinessUnitsQuery>);

    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: {
        items: [
          {
            id: "an-1",
            analysis_name: "Pliego Aprobado",
            business_unit: "CEDI",
            business_status: "no_aprobada",
            status: "analyzed",
            current_stage: "completed",
            progress_percentage: 100,
            created_at: "2026-09-23T12:00:00Z",
          },
          {
            id: "an-2",
            analysis_name: "Pliego Perdido",
            business_unit: "CEDI",
            business_status: "perdida",
            status: "analyzed",
            current_stage: "completed",
            progress_percentage: 100,
            created_at: "2026-09-23T11:00:00Z",
          },
        ],
        page: 1,
        per_page: 20,
        total: 2,
        total_pages: 1,
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Pliego Aprobado")).toBeInTheDocument();
    expect(screen.getByText("Pliego Perdido")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /no aprobadas/i }));

    expect(screen.getByText("Pliego Aprobado")).toBeInTheDocument();
    expect(screen.queryByText("Pliego Perdido")).not.toBeInTheDocument();
  });

  test("muestra el modal de duplicados al iniciar desde el Home en vez de dejar el analisis bloqueado", async () => {
    vi.mocked(useAnalysisBusinessUnitsQuery).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysisBusinessUnitsQuery>);

    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: {
        items: [
          {
            id: "an-1",
            analysis_name: "Pliego en cola",
            business_unit: "CEDI",
            status: "draft",
            current_stage: "queued",
            progress_percentage: 0,
            created_at: "2026-09-23T12:00:00Z",
          },
        ],
        page: 1,
        per_page: 20,
        total: 1,
        total_pages: 1,
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    vi.mocked(startAnalysis).mockResolvedValueOnce({
      id: "an-1",
      status: "draft",
      message: "Se detectaron documentos duplicados.",
      requires_resolution: true,
      duplicates: [
        {
          document_id: "doc-1",
          filename: "Pliego - Bancor.pdf",
          existing_analysis_id: "analysis-existente",
          created_at: "2026-09-03T10:00:00Z",
          created_by: "Agostina Torres",
          status: "completed",
        },
      ],
    });

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Iniciar análisis" }));

    expect(await screen.findByText("Documentos ya analizados")).toBeInTheDocument();
    expect(screen.getByText("Pliego - Bancor.pdf")).toBeInTheDocument();
    expect(
      screen.queryByText(/requiere resolver duplicados desde el wizard/i),
    ).not.toBeInTheDocument();

    vi.mocked(startAnalysis).mockResolvedValueOnce({
      id: "an-1",
      status: "queued",
      message: "Análisis encolado exitosamente.",
      requires_resolution: false,
      duplicates: [],
    });

    fireEvent.click(screen.getByRole("button", { name: /Confirmar decisiones/i }));

    await waitFor(() => {
      expect(screen.queryByText("Documentos ya analizados")).not.toBeInTheDocument();
    });

    expect(vi.mocked(startAnalysis).mock.calls[1]).toEqual([
      "an-1",
      { decisions: [{ document_id: "doc-1", action: "view_existing" }] },
    ]);
  });
});

describe("useAnalysisFilters", () => {
  test("aplica debounce de 300ms en búsqueda", () => {
    vi.useFakeTimers();

    function Probe() {
      const { searchInput, setSearchInput, filters } = useAnalysisFilters();
      return (
        <>
          <input
            aria-label="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
          <span data-testid="debounced-search">{filters.search ?? ""}</span>
        </>
      );
    }

    render(<Probe />);

    fireEvent.change(screen.getByLabelText("search"), { target: { value: "pliego salud" } });
    expect(screen.getByTestId("debounced-search").textContent).toBe("");

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(screen.getByTestId("debounced-search").textContent).toBe("");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByTestId("debounced-search").textContent).toBe("pliego salud");

    vi.useRealTimers();
  });

  test("muestra los próximos eventos y lleva al timeline del análisis al hacer click", async () => {
    vi.mocked(getUpcomingEvents).mockResolvedValue([
      {
        analysis_id: "analysis-9",
        analysis_name: "Servicio de conectividad",
        organismo: "Ministerio de Salud",
        business_status: "en_revision",
        business_unit: "CEDI",
        event_id: "event-1",
        event_name: "Presentación de ofertas",
        event_date: "2026-10-03",
        days_until: 3,
        additional_events: 1,
      },
    ]);
    vi.mocked(useAnalysesQuery).mockReturnValue({
      data: { items: [], page: 1, per_page: 20, total: 0, total_pages: 1 },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useAnalysesQuery>);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter>
            <Dashboard />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );

    const alert = await screen.findByTestId("expiring-alert-analysis-9-event-1");
    expect(alert).toHaveTextContent("Presentación de ofertas");
    expect(alert).toHaveTextContent("Servicio de conectividad");
    expect(alert).toHaveTextContent("03/10/2026");

    fireEvent.click(alert);

    expect(mockNavigate).toHaveBeenCalledWith("/analysis/analysis-9?tab=timeline");
  });
});
