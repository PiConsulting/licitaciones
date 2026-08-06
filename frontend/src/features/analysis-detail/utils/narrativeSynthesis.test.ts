import { buildNarrativeSynthesis } from "./narrativeSynthesis";
import type { CategoryData, FieldItem } from "../types";

function createField(
  field_name: string,
  options?: {
    state?: FieldItem["field_state"];
    value?: string | null;
  },
): FieldItem {
  return {
    field_name,
    field_value: options?.value ?? "valor",
    field_state: options?.state ?? "extraido",
    confidence: 0.9,
    citations: [
      {
        text: "Cita de prueba",
        page: 4,
        document_id: "doc-1",
        document_name: "Pliego.pdf",
      },
    ],
  };
}

function createCategory(items: FieldItem[], summary = "Resumen de prueba"): CategoryData {
  return {
    items,
    confidence: 0.8,
    source_references: [],
    extraction_status: "success",
    summary,
    is_reviewed: false,
  };
}

describe("buildNarrativeSynthesis", () => {
  test("devuelve párrafo único cuando no supera umbral", () => {
    const category = createCategory([
      createField("objeto", { value: "Compra de equipamiento" }),
      createField("modalidad", { value: "Licitación pública" }),
    ]);

    const synthesis = buildNarrativeSynthesis(category, "objeto_alcance");

    expect(synthesis.bullets).toHaveLength(0);
    expect(synthesis.text).toContain("objeto: Compra de equipamiento");
    expect(synthesis.hasUsefulData).toBe(true);
  });

  test("devuelve bullets cuando cantidad de ítems supera umbral", () => {
    const category = createCategory([
      createField("criterio_1", { value: "Precio" }),
      createField("criterio_2", { value: "Calidad" }),
      createField("criterio_3", { value: "Plazo" }),
      createField("criterio_4", { value: "Garantía" }),
    ]);

    const synthesis = buildNarrativeSynthesis(category, "criterios_evaluacion");

    expect(synthesis.bullets).toHaveLength(4);
    expect(synthesis.intro).toBeTruthy();
  });

  test("devuelve fallback cuando no hay datos útiles", () => {
    const category = createCategory([
      createField("garantia_anticipo", { state: "no_encontrado", value: null }),
    ], "Sin datos extraídos todavía.");

    const synthesis = buildNarrativeSynthesis(category, "garantias");

    expect(synthesis.hasUsefulData).toBe(false);
    expect(synthesis.bullets).toHaveLength(0);
    expect(synthesis.text).toContain("No se encontró información útil");
  });
});
