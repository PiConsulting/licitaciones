import type { CategoryData, FieldItem } from "../types";
import { buildCategoryNarrative } from "./categoryNarrative";

function field(field_name: string, field_state: FieldItem["field_state"], value: string | null = "valor"): FieldItem {
  return { field_name, field_value: value, field_state, confidence: 0.9, citations: [] };
}

function category(items: FieldItem[]): CategoryData {
  return {
    items,
    confidence: 0.8,
    source_references: [],
    extraction_status: "success",
    summary: "Resumen",
    is_reviewed: false,
  };
}

describe("buildCategoryNarrative", () => {
  test("categoría sin campos devuelve un párrafo indicando que no se encontró información", () => {
    const narrative = buildCategoryNarrative(category([]), "garantias");

    expect(narrative).toBe("No se encontró información sobre garantías en el pliego.");
  });

  test("campo extraído se redacta con su nombre y valor", () => {
    const narrative = buildCategoryNarrative(
      category([field("Monto de garantía", "extraido", "5%")]),
      "garantias",
    );

    expect(narrative).toContain("Monto de garantía: 5%.");
  });

  test("campo no encontrado se redacta como tal", () => {
    const narrative = buildCategoryNarrative(
      category([field("Garantía técnica", "no_encontrado", null)]),
      "garantias",
    );

    expect(narrative).toContain("No se encontró información sobre garantía técnica.");
  });

  test("campo no aplica se redacta como tal", () => {
    const narrative = buildCategoryNarrative(
      category([field("Garantía de anticipo", "no_aplica", null)]),
      "garantias",
    );

    expect(narrative).toContain("Garantía de anticipo no aplica para este pliego.");
  });

  test("campo en conflicto se redacta indicando el conflicto", () => {
    const narrative = buildCategoryNarrative(
      category([field("Monto de garantía", "en_conflicto", null)]),
      "garantias",
    );

    expect(narrative).toContain("Monto de garantía presenta valores en conflicto entre los documentos analizados.");
  });

  test("varios campos se concatenan en un solo párrafo", () => {
    const narrative = buildCategoryNarrative(
      category([field("A", "extraido", "1"), field("B", "no_encontrado", null)]),
      "plazos_clave",
    );

    expect(narrative).toBe("A: 1. No se encontró información sobre b.");
  });
});
