import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnalysisDetailPage } from "./AnalysisDetailPage";
import type { AnalysisDetail } from "./types";

const mockGetAnalysisById = vi.fn();
vi.mock("../../services/api/analysisApi", () => ({
  getAnalysisById: (...args: unknown[]) => mockGetAnalysisById(...args),
}));

vi.mock("../pdf-viewer/PDFViewer", () => ({
  PDFViewer: ({ documentId, citations }: { documentId: string; citations: unknown[] }) => (
    <div data-testid="pdf-viewer-mock">{`viewer:${documentId}:${citations.length}`}</div>
  ),
}));

function createAnalysis(): AnalysisDetail {
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
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AnalysisDetailPage analysisId="analysis-1" />
    </QueryClientProvider>,
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

  test("click en fuente de categoría (documento + página) abre visor en la cita elegida", async () => {
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Pliego Principal.pdf · pág. 15/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Pliego Principal.pdf · pág. 15/i }));

    expect(screen.getByTestId("pdf-viewer-mock")).toHaveTextContent("viewer:doc-1:1");
  });
});
