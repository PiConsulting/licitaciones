import { render, screen } from "@testing-library/react";

import { AnalysisStatusPolling } from "./AnalysisStatusPolling";

describe("AnalysisStatusPolling", () => {
  test("muestra etapa de analizando categorías", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-0",
          status: "processing",
          current_stage: "analyzing",
          progress_percentage: 45,
          stage_progress: "Analizando categorias (5 de 8)",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText(/Analizando categorias/i)).toBeInTheDocument();
  });

  test("muestra estado Extrayendo texto", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-1",
          status: "processing",
          current_stage: "extracting_text",
          progress_percentage: 15,
          stage_progress: "Extrayendo texto (1 de 3 documentos)",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getAllByText(/Extrayendo texto/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 de 3 documentos/i)).toBeInTheDocument();
  });

  test("muestra estado Indexando documentos", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-2",
          status: "processing",
          current_stage: "indexing",
          progress_percentage: 25,
          stage_progress: "Indexando (vector store activo)",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getAllByText(/Indexando/i).length).toBeGreaterThan(0);
  });

  test("muestra mensaje de error", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-3",
          status: "error",
          current_stage: "completed",
          progress_percentage: 35,
          stage_progress: "Analizado",
          error_message: "No se pudo leer el texto de pliego.pdf",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText(/Analizado/i)).toBeInTheDocument();
  });

  test("muestra advertencia cuando hay categorías fallidas", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-4",
          status: "analyzed",
          current_stage: "completed",
          progress_percentage: 100,
          stage_progress: "Analizado",
          extracted_data: {
            plazos_extraction_status: "failed",
            garantias_extraction_status: "success",
          },
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText(/Análisis completo con advertencias/i)).toBeInTheDocument();
    expect(screen.getByText(/Algunas categorías no pudieron extraerse/i)).toBeInTheDocument();
  });
});
