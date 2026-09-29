import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { ToastProvider } from "../../components/ToastContainer";
import type { BusinessState, BusinessStatus } from "../../types/businessStatus";
import { AnalysisDetailPage } from "./AnalysisDetailPage";
import type { AnalysisDetail, CategoryData } from "./types";

const mockGetAnalysisById = vi.fn();
const mockGetBusinessState = vi.fn();
const mockDecideAnalysisCategories = vi.fn();

vi.mock("../../services/api/analysisApi", () => ({
  getAnalysisById: (...args: unknown[]) => mockGetAnalysisById(...args),
}));

vi.mock("../../api/businessStatus", () => ({
  getBusinessState: (...args: unknown[]) => mockGetBusinessState(...args),
  updateBusinessStatus: vi.fn(),
  savePresentation: vi.fn(),
  saveResult: vi.fn(),
}));

vi.mock("../../api/analyses", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/analyses")>();
  return {
    ...actual,
    getAnalysisStatus: vi.fn().mockResolvedValue({
      id: "analysis-1",
      status: "analyzed",
      current_stage: "completed",
      progress_percentage: 100,
    }),
    decideAnalysisCategories: (...args: unknown[]) => mockDecideAnalysisCategories(...args),
  };
});

vi.mock("../../api/timeline", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/timeline")>();
  return { ...actual, getTimelineEvents: vi.fn().mockResolvedValue([]) };
});

vi.mock("../pdf-viewer/PDFViewer", () => ({
  PDFViewer: () => <div data-testid="pdf-viewer-mock" />,
}));

const EMPTY_CATEGORY: CategoryData = {
  items: [],
  confidence: 0,
  source_references: [],
  extraction_status: "not_found",
  summary: "",
  is_reviewed: false,
};

function createAnalysis(overrides: Partial<AnalysisDetail> = {}): AnalysisDetail {
  const createdAt = new Date().toISOString();
  return {
    id: "analysis-1",
    created_at: createdAt,
    status: "analyzed",
    current_stage: "completed",
    current_version: {
      id: "v1",
      version_number: 1,
      extracted_data: {
        objeto_alcance: EMPTY_CATEGORY,
        riesgos: EMPTY_CATEGORY,
        requisitos_admisibilidad: EMPTY_CATEGORY,
        garantias: EMPTY_CATEGORY,
        plazos_clave: EMPTY_CATEGORY,
        criterios_evaluacion: EMPTY_CATEGORY,
        causales_rechazo: EMPTY_CATEGORY,
        anexos_obligatorios: EMPTY_CATEGORY,
        datos_procedimiento: EMPTY_CATEGORY,
      },
      conflicts: {},
      created_at: createdAt,
    },
    documents: [{ id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true, page_count: 20 }],
    ...overrides,
  };
}

function buildState(status: BusinessStatus): BusinessState {
  return { id: "analysis-1", business_status: status, presentation: null, result: null, history: [] };
}

function renderPage(entry = "/analysis/analysis-1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/analysis/:analysisId" element={<AnalysisDetailPage analysisId="analysis-1" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("AnalysisDetailPage pestaña Estado", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("marca la pestaña Estado con un punto cuando hay una acción pendiente", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ business_status: "pendiente_decision" }));
    renderPage();

    expect(await screen.findByTestId("estado-pending-dot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Estado" })).toBeInTheDocument();
  });

  it("abre la pestaña Timeline cuando la URL trae tab=timeline", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ business_status: "en_revision" }));
    mockGetBusinessState.mockResolvedValue(buildState("en_revision"));
    renderPage("/analysis/analysis-1?tab=timeline");

    const timelineTab = await screen.findByRole("button", { name: "Timeline" });
    await waitFor(() => expect(timelineTab).toHaveAttribute("aria-current", "page"));
  });

  it("ignora un tab desconocido en la URL", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ business_status: "en_revision" }));
    mockGetBusinessState.mockResolvedValue(buildState("en_revision"));
    renderPage("/analysis/analysis-1?tab=inexistente");

    const previewTab = await screen.findByRole("button", { name: "Preview" });
    expect(previewTab).toHaveAttribute("aria-current", "page");
  });

  it("no muestra el punto cuando la licitación ya terminó", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ business_status: "ganada" }));
    renderPage();

    await screen.findByRole("button", { name: "Estado" });
    expect(screen.queryByTestId("estado-pending-dot")).not.toBeInTheDocument();
  });

  it("abre la pestaña Estado desde el badge del encabezado", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ business_status: "en_revision" }));
    mockGetBusinessState.mockResolvedValue(buildState("en_revision"));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByTestId("business-status-badge"));

    expect(await screen.findByTestId("estado-tab-content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Estado" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByTestId("business-revision-card")).toBeInTheDocument();
  });

  it("muestra la decisión también en Preview mientras está pendiente, con el mismo componente que Estado", async () => {
    mockGetAnalysisById.mockResolvedValue(
      createAnalysis({ status: "en_revision", business_status: "pendiente_decision" }),
    );
    renderPage();

    expect(await screen.findByTestId("business-decision-panel")).toBeInTheDocument();
    expect(screen.getByText("¿Aprobamos esta licitación para el análisis completo?")).toBeInTheDocument();
  });

  it("oculta la decisión de Preview cuando la licitación ya fue aprobada", async () => {
    mockGetAnalysisById.mockResolvedValue(
      createAnalysis({ status: "en_revision", business_status: "en_revision" }),
    );
    renderPage();

    await screen.findByTestId("preview-tab-content");
    expect(screen.queryByTestId("business-decision-panel")).not.toBeInTheDocument();
  });

  it("permite volver a decidir en Preview cuando se reabrió una licitación rechazada", async () => {
    mockGetAnalysisById.mockResolvedValue(
      createAnalysis({
        status: "en_revision",
        business_status: "pendiente_decision",
        categories_decision: "rejected",
      }),
    );
    renderPage();

    expect(await screen.findByTestId("business-decision-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("categories-decision-rejected-banner")).not.toBeInTheDocument();
  });

  it("aprobar desde Estado dispara el flujo de categorías, actualiza el badge y oculta la decisión también en Preview", async () => {
    mockGetAnalysisById.mockResolvedValue(
      createAnalysis({ status: "en_revision", business_status: "pendiente_decision" }),
    );
    mockGetBusinessState.mockResolvedValue(buildState("pendiente_decision"));
    mockDecideAnalysisCategories.mockImplementation(async () => {
      mockGetAnalysisById.mockResolvedValue(
        createAnalysis({ status: "analyzed", business_status: "en_revision", categories_decision: "approved" }),
      );
      return {
        id: "analysis-1",
        status: "queued",
        message: "ok",
        decision: "approved",
        decision_by_name: "Agostina Torres",
        decision_at: new Date().toISOString(),
      };
    });
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByTestId("business-decision-panel")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Estado" }));
    await user.click(await screen.findByRole("button", { name: /Aprobar y analizar Fase 2/ }));

    await waitFor(() => expect(mockDecideAnalysisCategories).toHaveBeenCalledWith("analysis-1", "approved"));
    await waitFor(() => expect(screen.getByTestId("business-status-badge")).toHaveTextContent("En revisión"));

    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(screen.queryByTestId("business-decision-panel")).not.toBeInTheDocument();
  });
});
