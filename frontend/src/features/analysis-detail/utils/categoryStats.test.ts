import { getAnalysisSummary, getCategoryCounts } from "./categoryStats";
import type { AnalysisDetail, CategoryData, CategoryId, FieldItem } from "../types";

function field(field_name: string, field_state: FieldItem["field_state"]): FieldItem {
  return {
    field_name,
    field_value: "valor",
    field_state,
    confidence: 0.9,
    citations: [],
  };
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

describe("getCategoryCounts", () => {
  test("cuenta cada field_state, incluyendo no_aplica", () => {
    const counts = getCategoryCounts(
      category([
        field("a", "extraido"),
        field("b", "extraido"),
        field("c", "no_encontrado"),
        field("d", "en_conflicto"),
        field("e", "no_aplica"),
      ]),
    );

    expect(counts).toEqual({ extracted: 2, notFound: 1, conflict: 1, notApplicable: 1, total: 5 });
  });

  test("categoría vacía da todos los conteos en cero", () => {
    expect(getCategoryCounts(category([]))).toEqual({
      extracted: 0,
      notFound: 0,
      conflict: 0,
      notApplicable: 0,
      total: 0,
    });
  });
});

describe("getAnalysisSummary", () => {
  function analysisWith(categories: Partial<Record<CategoryId, CategoryData>>): AnalysisDetail {
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

  test("suma los conteos de todas las categorías presentes", () => {
    const analysis = analysisWith({
      objeto_alcance: category([field("a", "extraido"), field("b", "no_encontrado")]),
      garantias: category([field("c", "en_conflicto")]),
    });

    const summary = getAnalysisSummary(analysis);
    expect(summary.totalFields).toBe(3);
    expect(summary.extracted).toBe(1);
    expect(summary.notFound).toBe(1);
    expect(summary.conflict).toBe(1);
  });

  test("marca como 'necesita revisión' las categorías críticas sin revisar y las que tienen conflictos", () => {
    const analysis = analysisWith({
      garantias: category([], { is_reviewed: false }), // crítica, sin revisar
      plazos_clave: category([], { is_reviewed: true }), // crítica, ya revisada
      objeto_alcance: category([field("a", "en_conflicto")]), // no crítica, con conflicto
      criterios_evaluacion: category([field("b", "extraido")]), // no crítica, sin conflicto
    });

    const summary = getAnalysisSummary(analysis);
    expect(summary.categoriesNeedingReview).toContain("garantias");
    expect(summary.categoriesNeedingReview).toContain("objeto_alcance");
    expect(summary.categoriesNeedingReview).not.toContain("plazos_clave");
    expect(summary.categoriesNeedingReview).not.toContain("criterios_evaluacion");
  });

  test("categorías ausentes en extracted_data no rompen el cálculo", () => {
    const summary = getAnalysisSummary(analysisWith({}));
    expect(summary.totalFields).toBe(0);
    expect(summary.categoriesNeedingReview).toEqual([]);
  });

  test("cuenta categoría not_applicable como categoría completa", () => {
    const summary = getAnalysisSummary(
      analysisWith({
        garantias: category([], { extraction_status: "not_applicable" }),
      }),
    );

    expect(summary.totalCategories).toBe(1);
    expect(summary.extractedCategories).toBe(1);
    expect(summary.notApplicable).toBe(0);
  });
});
