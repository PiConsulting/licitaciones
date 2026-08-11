import { render, screen } from "@testing-library/react";

import { AnalysisSummaryStrip } from "./AnalysisSummaryStrip";
import type { AnalysisDetail, CategoryData, CategoryId, FieldItem } from "./types";

function field(field_name: string, field_state: FieldItem["field_state"]): FieldItem {
  return { field_name, field_value: "valor", field_state, confidence: 0.9, citations: [] };
}

function category(items: FieldItem[], overrides?: Partial<CategoryData>): CategoryData {
  return {
    items,
    confidence: 0.8,
    source_references: [],
    extraction_status: "success",
    summary: "Resumen",
    is_reviewed: false,
    ...overrides,
  };
}

function createAnalysis(categories: Partial<Record<CategoryId, CategoryData>>): AnalysisDetail {
  return {
    id: "analysis-1",
    created_at: new Date().toISOString(),
    status: "analyzed",
    current_stage: "completed",
    current_version: {
      id: "v1",
      version_number: 1,
      extracted_data: categories as Record<CategoryId, CategoryData>,
      conflicts: {},
      created_at: new Date().toISOString(),
    },
    documents: [],
  };
}

describe("AnalysisSummaryStrip", () => {
  test("muestra el total de categorías extraídas", () => {
    const analysis = createAnalysis({
      objeto_alcance: category([field("a", "extraido"), field("b", "no_encontrado")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.getByText("1/1 categorías extraídas")).toBeInTheDocument();
  });

  test("no muestra chips de revisión hasta implementar la lógica de revisión", () => {
    const analysis = createAnalysis({
      garantias: category([], { is_reviewed: false }),
      criterios_evaluacion: category([field("a", "extraido")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.queryByText(/Necesitan revisión/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Garantías/i })).not.toBeInTheDocument();
  });

  test("sin categorías pendientes, no muestra la sección de chips", () => {
    const analysis = createAnalysis({
      criterios_evaluacion: category([field("a", "extraido")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.queryByText(/Necesitan revisión/i)).not.toBeInTheDocument();
  });

  test("cuenta categoría no_aplicable como completa para el ratio", () => {
    const analysis = createAnalysis({
      objeto_alcance: category([field("a", "extraido")]),
      requisitos_admisibilidad: category([field("b", "extraido")]),
      garantias: category([], { extraction_status: "not_applicable" }),
      plazos_clave: category([field("d", "extraido")]),
      criterios_evaluacion: category([field("e", "extraido")]),
      causales_rechazo: category([field("f", "extraido")]),
      anexos_obligatorios: category([field("g", "extraido")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.getByText("7/7 categorías extraídas")).toBeInTheDocument();
  });

  describe("AC3: Orden consistente con CATEGORY_ORDER", () => {
    test("debe contar solo las 7 categorías canónicas (sin datos_procedimiento)", () => {
      const analysis = createAnalysis({
        objeto_alcance: category([field("a", "extraido")]),
        requisitos_admisibilidad: category([field("b", "extraido")]),
        garantias: category([field("c", "extraido")]),
        plazos_clave: category([field("d", "extraido")]),
        criterios_evaluacion: category([field("e", "extraido")]),
        causales_rechazo: category([field("f", "extraido")]),
        anexos_obligatorios: category([field("g", "extraido")]),
        datos_procedimiento: category([field("h", "extraido")]), // NO debe contarse
      });

      render(<AnalysisSummaryStrip analysis={analysis} />);

      // Debe mostrar 7/7, no 8/8
      expect(screen.getByText("7/7 categorías extraídas")).toBeInTheDocument();
    });

    test("NO debe mostrar chip para datos_procedimiento aunque necesite revisión", () => {
      const analysis = createAnalysis({
        datos_procedimiento: category([field("a", "en_conflicto")]),
        garantias: category([], { is_reviewed: false }),
      });

      render(<AnalysisSummaryStrip analysis={analysis} />);

      // Los chips están ocultos temporalmente.
      expect(screen.queryByRole("button", { name: /Datos del Procedimiento/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Garantías/i })).not.toBeInTheDocument();
    });
  });
});
