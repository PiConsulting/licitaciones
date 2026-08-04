import { render, screen } from "@testing-library/react";

import { AnalysisStatusPolling } from "./AnalysisStatusPolling";

describe("AnalysisStatusPolling", () => {
  test("muestra etapa de analizando categorías", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-0",
          status: "analyzing",
          current_stage: "Analizando categorías (5/8 completadas)",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText(/Analizando categorías/i)).toBeInTheDocument();
  });

  test("muestra estado Extrayendo texto", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-1",
          status: "extracting_text",
          current_stage: "Extrayendo texto (1 de 3 documentos)",
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
          status: "indexing",
          current_stage: "Indexando documentos",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getAllByText(/Indexando documentos/i).length).toBeGreaterThan(0);
  });

  test("muestra mensaje de error", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-3",
          status: "error",
          current_stage: "No se pudo leer el texto de «pliego.pdf»",
        }}
        isLoading={false}
        error={null}
      />,
    );

    expect(screen.getByText(/No se pudo leer el texto/i)).toBeInTheDocument();
  });

  test("muestra advertencia cuando hay categorías fallidas", () => {
    render(
      <AnalysisStatusPolling
        statusData={{
          id: "analysis-4",
          status: "analyzed",
          current_stage: "Análisis completo",
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
