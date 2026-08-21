import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ToastProvider } from "../../components/ToastContainer";
import { AnalysisDetailPage } from "./AnalysisDetailPage";
import type { AnalysisDetail } from "./types";
import type { AnalysisTracking } from "../../types/tracking";

const mockGetAnalysisById = vi.fn();
vi.mock("../../services/api/analysisApi", () => ({
  getAnalysisById: (...args: unknown[]) => mockGetAnalysisById(...args),
}));

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
  return {
    id: "analysis-1",
    created_at: new Date().toISOString(),
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
    documents: [
      { id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true, page_count: 20 },
    ],
    tracking: options?.tracking,
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

describe("AnalysisDetailPage PDF integration", () => {
  beforeEach(() => {
    mockGetAnalysisById.mockResolvedValue(createAnalysis());
    sessionStorage.clear();
  });

  test("carga el documento primario por default, sin necesidad de seleccionar una cita", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("pdf-viewer-mock")).toBeInTheDocument();
    });

    expect(screen.getByTestId("pdf-viewer-mock")).toHaveTextContent("viewer:doc-1:0");
  });

  test("la vista divide PDF y campos en contenedores inferiores con anchos xl esperados", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("categories-panel")).toBeInTheDocument();
    });

    expect(screen.getByTestId("detail-summary-panel")).toBeInTheDocument();
    expect(screen.getByTestId("categories-panel")).toHaveClass("xl:w-[60%]");
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
    expect(screen.getByTestId("categories-panel")).toHaveClass("xl:w-full");

    await user.click(screen.getByRole("button", { name: "Mostrar PDF" }));

    expect(screen.getByTestId("pdf-viewer-panel")).toBeInTheDocument();
    expect(screen.getByTestId("categories-panel")).toHaveClass("xl:w-[60%]");
  });

  test("click en fuente de categoría (documento + página) abre visor en la cita elegida", async () => {
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Pliego Principal\.pdf · pág. 15/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Pliego Principal\.pdf · pág. 15/i }));

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

    await user.click(screen.getByRole("button", { name: /Pliego Principal\.pdf · pág. 15/i }));

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
      expect(screen.getByTestId("categories-panel")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Terminar seguimiento" })).not.toBeInTheDocument();
  });
});
