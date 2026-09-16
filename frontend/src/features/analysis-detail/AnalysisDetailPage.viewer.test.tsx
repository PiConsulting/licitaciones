import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ToastProvider } from "../../components/ToastContainer";
import { AnalysisDetailPage } from "./AnalysisDetailPage";
import type { AnalysisDetail } from "./types";
import type { AnalysisTracking } from "../../types/tracking";

const mockGetAnalysisById = vi.fn();
const mockGetAnalysisStatus = vi.fn();
const mockStartAnalysisCategories = vi.fn();
const mockReanalyzeAnalysis = vi.fn();
vi.mock("../../services/api/analysisApi", () => ({
  getAnalysisById: (...args: unknown[]) => mockGetAnalysisById(...args),
}));

vi.mock("../../api/analyses", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/analyses")>();
  return {
    ...actual,
    getAnalysisStatus: (...args: unknown[]) => mockGetAnalysisStatus(...args),
    startAnalysisCategories: (...args: unknown[]) => mockStartAnalysisCategories(...args),
    reanalyzeAnalysis: (...args: unknown[]) => mockReanalyzeAnalysis(...args),
  };
});

vi.mock("../pdf-viewer/PDFViewer", () => ({
  PDFViewer: ({ documentId, citations, onClose }: { documentId: string; citations: unknown[]; onClose?: () => void }) => (
    <div data-testid="pdf-viewer-mock">
      <span>{`viewer:${documentId}:${citations.length}`}</span>
      {onClose ? (
        <button type="button" onClick={onClose} aria-label="Ocultar visor PDF">
          Ocultar visor PDF
        </button>
      ) : null}
    </div>
  ),
}));

function createTracking(status: "active" | "completed"): AnalysisTracking {
  return {
    id: "tracking-1",
    type: "tracking",
    analysis_id: "analysis-1",
    version_id: "v1",
    status,
    started_by: "user-1",
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    categories: [],
    summary: {
      total_categories: 7,
      not_reviewed: 0,
      in_review: 7,
      closed: 0,
      closed_percentage: 0,
    },
  };
}

function createAnalysis(options?: { tracking?: AnalysisTracking | null }): AnalysisDetail {
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
        objeto_alcance: {
          confidence: 0.6,
          extraction_status: "success",
          is_reviewed: false,
          summary: "Resumen",
          source_references: [],
          items: [
            {
              field_name: "Objeto",
              field_value: "Adquisicion",
              field_state: "extraido",
              confidence: 0.6,
              citations: [
                {
                  text: "Texto cita",
                  page: 15,
                  document_id: "doc-1",
                  document_name: "Pliego Principal.pdf",
                },
              ],
            },
          ],
        },
        requisitos_admisibilidad: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        garantias: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        plazos_clave: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        criterios_evaluacion: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        causales_rechazo: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        anexos_obligatorios: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        datos_procedimiento: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
      },
      conflicts: {},
      created_at: new Date().toISOString(),
    },
    versions: [
      {
        id: "v2",
        version_number: 2,
        extracted_data: {
          objeto_alcance: {
            confidence: 0.72,
            extraction_status: "success",
            is_reviewed: false,
            summary: "Objeto actualizado",
            source_references: [],
            items: [
              {
                field_name: "Objeto",
                field_value: "Adquisicion actualizada",
                field_state: "extraido",
                confidence: 0.72,
                citations: [],
              },
            ],
          },
          riesgos: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          requisitos_admisibilidad: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          garantias: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          plazos_clave: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          criterios_evaluacion: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          causales_rechazo: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          anexos_obligatorios: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          datos_procedimiento: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        },
        conflicts: {},
        created_at: createdAt,
      },
      {
        id: "v1",
        version_number: 1,
        extracted_data: {
          objeto_alcance: {
            confidence: 0.6,
            extraction_status: "success",
            is_reviewed: false,
            summary: "Resumen",
            source_references: [],
            items: [
              {
                field_name: "Objeto",
                field_value: "Adquisicion",
                field_state: "extraido",
                confidence: 0.6,
                citations: [],
              },
            ],
          },
          riesgos: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          requisitos_admisibilidad: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          garantias: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          plazos_clave: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          criterios_evaluacion: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          causales_rechazo: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          anexos_obligatorios: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
          datos_procedimiento: { confidence: 0, extraction_status: "not_found", is_reviewed: false, summary: "", source_references: [], items: [] },
        },
        conflicts: {},
        created_at: createdAt,
      },
    ],
    documents: [
      { id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true, page_count: 20 },
    ],
    tracking: options?.tracking,
  };
}

function createAnalysisInReview(): AnalysisDetail {
  return {
    ...createAnalysis(),
    status: "en_revision",
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <ToastProvider>
      <QueryClientProvider client={queryClient}>
        <AnalysisDetailPage analysisId="analysis-1" />
      </QueryClientProvider>
    </ToastProvider>,
  );
}

function getPreviewSourceButton() {
  return (
    screen.queryByRole("button", { name: /Ver fuente en el pliego \(pág\. 15\)/i }) ??
    screen.queryByRole("button", { name: /Pliego Principal\.pdf · pág\. 15/i })
  );
}

describe("AnalysisDetailPage PDF integration", () => {
  beforeEach(() => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis());
    mockGetAnalysisStatus.mockResolvedValue({
      id: "analysis-1",
      status: "processing",
      current_stage: "analyzing",
      progress_percentage: 55,
      stage_progress: "Analizando Preview (2 de 3)",
    });
    mockStartAnalysisCategories.mockResolvedValue({
      id: "analysis-1",
      status: "queued",
      message: "Análisis de categorías encolado exitosamente.",
      requires_resolution: false,
      duplicates: [],
      redirect_analysis_id: null,
    });
    mockReanalyzeAnalysis.mockResolvedValue({
      id: "analysis-1",
      status: "queued",
      message: "Reanálisis encolado",
      reanalysis_type: "all",
      categories: [],
      source_version_id: "v2",
      target_version_id: "v3",
      target_version_number: 3,
    });
    sessionStorage.clear();
  });

  test("carga el documento primario por default, sin necesidad de seleccionar una cita", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("pdf-viewer-mock")).toBeInTheDocument();
    });

    expect(screen.getByTestId("pdf-viewer-mock")).toHaveTextContent("viewer:doc-1:0");
  });

  test("usa Preview como pestaña inicial por defecto", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("preview-tab-content")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-current", "page");
  });

  test("si falta preview_criterios en análisis legacy, mantiene preview funcional y muestra nota informativa", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("preview-tab-content")).toBeInTheDocument();
    });

    expect(screen.getByTestId("preview-tab-legacy-note")).toBeInTheDocument();
    expect(screen.getByTestId("narrative-blocks")).toBeInTheDocument();
  });

  test("en análisis legacy, Categorías y Timeline siguen operativos sin romper la vista", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("preview-tab-legacy-note")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Categorías" }));
    expect(screen.getByRole("button", { name: "Categorías" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Categorías de análisis")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Timeline" }));
    expect(screen.getByRole("button", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Timeline" })).toBeInTheDocument();
    });
  });

  test("la vista divide PDF y campos en contenedores inferiores con anchos xl esperados", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("analysis-content-panel")).toBeInTheDocument();
    });

    expect(screen.getByTestId("detail-summary-panel")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-content-panel")).toHaveClass("xl:w-[60%]");
    expect(screen.getByTestId("pdf-viewer-panel")).toHaveClass("xl:w-[40%]");
  });

  test("puede ocultar y mostrar el visor PDF para revisar categorías a ancho completo", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("pdf-viewer-panel")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Ocultar visor PDF" }));

    expect(screen.queryByTestId("pdf-viewer-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("analysis-content-panel")).toHaveClass("xl:w-full");

    await user.click(screen.getByRole("button", { name: "Mostrar PDF" }));

    expect(screen.getByTestId("pdf-viewer-panel")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-content-panel")).toHaveClass("xl:w-[60%]");
  });

  test("click en fuente de categoría (documento + página) abre visor en la cita elegida", async () => {
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => {
      expect(getPreviewSourceButton()).toBeInTheDocument();
    });

    await user.click(getPreviewSourceButton()!);

    expect(screen.getByTestId("pdf-viewer-mock")).toHaveTextContent("viewer:doc-1:1");
  });

  test("si el visor está oculto, tocar una fuente lo vuelve a abrir con la cita seleccionada", async () => {
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Ocultar visor PDF" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Ocultar visor PDF" }));
    expect(screen.queryByTestId("pdf-viewer-panel")).not.toBeInTheDocument();

    await user.click(getPreviewSourceButton()!);

    expect(screen.getByTestId("pdf-viewer-panel")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-viewer-mock")).toHaveTextContent("viewer:doc-1:1");
  });

  test("muestra acción flotante de terminar seguimiento cuando tracking está activo", async () => {
    const user = userEvent.setup();
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ tracking: createTracking("active") }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Terminar seguimiento" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Terminar seguimiento" }));

    expect(screen.getByRole("heading", { name: "Terminar seguimiento" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Seguir editando" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar finalización" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Seguir editando" }));
    expect(screen.queryByRole("button", { name: "Confirmar finalización" })).not.toBeInTheDocument();
  });

  test("oculta acción terminar seguimiento cuando tracking está completado", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis({ tracking: createTracking("completed") }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("analysis-content-panel")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Terminar seguimiento" })).not.toBeInTheDocument();
  });

  test("muestra acción para iniciar análisis de categorías cuando el análisis está en revisión", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysisInReview());

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Iniciar análisis de categorías restantes" })).toBeInTheDocument();
    });
  });

  test("no muestra acción para iniciar categorías cuando el análisis ya está analyzed", async () => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis());

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("analysis-content-panel")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Iniciar análisis de categorías restantes" })).not.toBeInTheDocument();
  });

  test("al iniciar análisis de categorías, muestra barra de progreso del mismo componente", async () => {
    const user = userEvent.setup();
    mockGetAnalysisById.mockResolvedValue(createAnalysisInReview());

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Iniciar análisis de categorías restantes" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Iniciar análisis de categorías restantes" }));

    await waitFor(() => {
      expect(screen.getByTestId("categories-progress-panel")).toBeInTheDocument();
    });
  });

  test("si hay redirección pendiente persistida y el análisis ya terminó, abre Categorías por defecto", async () => {
    sessionStorage.setItem("analysis:analysis-1:redirect_to_categories_on_analyze", "1");
    mockGetAnalysisById.mockResolvedValue(createAnalysis());

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Categorías" })).toHaveAttribute("aria-current", "page");
    });
  });

  test("muestra pestaña Versiones con marcador de versión actual y vista histórica", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Versiones" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Versiones" }));

    expect(screen.getByTestId("versions-tab-content")).toBeInTheDocument();
    expect(screen.getByTestId("current-version-badge")).toBeInTheDocument();
    expect(screen.getByText(/Vista histórica - Versión 1|Vista histórica - Versión 2/i)).toBeInTheDocument();
  });

  test("modal Reanalizar valida categorías cuando se elige selección manual", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Reanalizar" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Reanalizar" }));
    expect(screen.getByTestId("reanalyze-modal")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Seleccionar categorías" }));

    const confirmButton = screen.getByRole("button", { name: "Confirmar reanálisis" });
    expect(confirmButton).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Riesgos" }));
    expect(confirmButton).not.toBeDisabled();

    await user.click(confirmButton);

    await waitFor(() => {
      expect(mockReanalyzeAnalysis).toHaveBeenCalledWith("analysis-1", {
        reanalysis_type: "categories",
        categories: ["riesgos"],
      });
    });
  });
});
