import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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

  test("muestra chips solo para categorías que necesitan revisión", () => {
    const analysis = createAnalysis({
      garantias: category([], { is_reviewed: false }),
      criterios_evaluacion: category([field("a", "extraido")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.getByRole("button", { name: /Garantías/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Criterios de Evaluación/i })).not.toBeInTheDocument();
  });

  test("click en un chip hace scroll a la sección de esa categoría", async () => {
    const user = userEvent.setup();
    const analysis = createAnalysis({
      garantias: category([], { is_reviewed: false }),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    const section = document.createElement("div");
    section.id = "category-garantias";
    const scrollIntoView = vi.fn();
    section.scrollIntoView = scrollIntoView;
    document.body.appendChild(section);

    await user.click(screen.getByRole("button", { name: /Garantías/i }));

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });

    document.body.removeChild(section);
  });

  test("sin categorías pendientes, no muestra la sección de chips", () => {
    const analysis = createAnalysis({
      criterios_evaluacion: category([field("a", "extraido")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.queryByText(/Necesitan revisión/i)).not.toBeInTheDocument();
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

    test("chips de revisión siguen el orden canónico de CATEGORY_ORDER", () => {
      const analysis = createAnalysis({
        objeto_alcance: category([field("a", "en_conflicto")]), // índice 0
        garantias: category([], { is_reviewed: false }), // índice 2 - crítica
        plazos_clave: category([], { is_reviewed: false }), // índice 3 - crítica
        anexos_obligatorios: category([field("b", "en_conflicto")]), // índice 6
      });

      render(<AnalysisSummaryStrip analysis={analysis} />);

      const buttons = screen.getAllByRole("button");

      // Los botones deben aparecer en el orden definido por CATEGORY_ORDER
      // (no en orden de criticidad)
      expect(buttons[0]).toHaveTextContent("Objeto y Alcance"); // índice 0
      expect(buttons[1]).toHaveTextContent("Garantías"); // índice 2
      expect(buttons[2]).toHaveTextContent("Plazos Clave"); // índice 3
      expect(buttons[3]).toHaveTextContent("Anexos Obligatorios"); // índice 6
    });

    test("NO debe mostrar chip para datos_procedimiento aunque necesite revisión", () => {
      const analysis = createAnalysis({
        datos_procedimiento: category([field("a", "en_conflicto")]),
        garantias: category([], { is_reviewed: false }),
      });

      render(<AnalysisSummaryStrip analysis={analysis} />);

      // Solo debe aparecer el chip de garantías
      expect(screen.getByRole("button", { name: /Garantías/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Datos del Procedimiento/i })).not.toBeInTheDocument();
    });
  });
});
