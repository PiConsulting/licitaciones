import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AnalysisSummaryStrip } from "./AnalysisSummaryStrip";
import { useAccordionState } from "./hooks/useAccordionState";
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
  beforeEach(() => {
    sessionStorage.clear();
    useAccordionState.setState({ expandedCategories: [], hasInitialized: false });
  });

  test("muestra el total de campos extraídos", () => {
    const analysis = createAnalysis({
      objeto_alcance: category([field("a", "extraido"), field("b", "no_encontrado")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.getByText("1/2 campos extraídos")).toBeInTheDocument();
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

  test("click en un chip expande esa categoría en el store", async () => {
    const user = userEvent.setup();
    const analysis = createAnalysis({
      garantias: category([], { is_reviewed: false }),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);
    await user.click(screen.getByRole("button", { name: /Garantías/i }));

    expect(useAccordionState.getState().expandedCategories).toContain("garantias");
  });

  test("sin categorías pendientes, no muestra la sección de chips", () => {
    const analysis = createAnalysis({
      criterios_evaluacion: category([field("a", "extraido")]),
    });

    render(<AnalysisSummaryStrip analysis={analysis} />);

    expect(screen.queryByText(/Necesitan revisión/i)).not.toBeInTheDocument();
  });
});
