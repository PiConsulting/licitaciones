/**
 * CTX-03: "no analizado" no es "no encontrado". Una categoría sin extractor
 * implementado todavía no puede reportar `not_found`, que en toda esta vista
 * significa "el pliego no lo dice" -- una afirmación sobre el pliego que el
 * sistema nunca verificó.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { CategorySection } from "./CategorySection";
import type { CategoryData } from "./types";

function categoria(status: CategoryData["extraction_status"]): CategoryData {
  return {
    items: [],
    confidence: 0,
    source_references: [],
    extraction_status: status,
    summary: "Sin resumen disponible.",
    is_reviewed: false,
  };
}

describe("categorías fuera del alcance del análisis", () => {
  test("una categoría no analizada se distingue de una sin hallazgos", () => {
    render(<CategorySection category={categoria("not_analyzed")} categoryId="datos_procedimiento" />);

    expect(screen.getByText(/NO ANALIZADA/i)).toBeInTheDocument();
  });

  test("una categoría vacía pendiente de fase 1 se muestra como 'no analizada'", () => {
    render(<CategorySection category={categoria("not_found")} categoryId="datos_procedimiento" />);

    expect(screen.getByText(/NO ANALIZADA/i)).toBeInTheDocument();
    expect(
      screen.getByText("Todavía no fue analizada. Se completa al analizar las categorías restantes."),
    ).toBeInTheDocument();
  });

  test("el estado nuevo no se confunde con 'no aplica'", () => {
    render(<CategorySection category={categoria("not_analyzed")} categoryId="datos_procedimiento" />);

    expect(screen.queryByText(/^NO APLICA$/i)).not.toBeInTheDocument();
  });

  test("en revisión, una categoría legacy con item no_encontrado igual se muestra como no analizada", () => {
    const category: CategoryData = {
      ...categoria("not_found"),
      items: [
        {
          field_name: "riesgos",
          field_value: "No encontrado",
          field_state: "no_encontrado",
          confidence: 0,
          citations: [],
        },
      ],
    };

    render(<CategorySection analysisStatus="en_revision" category={category} categoryId="riesgos" />);

    expect(screen.getByText(/NO ANALIZADA/i)).toBeInTheDocument();
    expect(screen.getByText("Todavía no fue analizada. Se completa al analizar las categorías restantes.")).toBeInTheDocument();
    expect(screen.queryByText(/No se encontró información sobre riesgos/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("category-sources-empty")).not.toBeInTheDocument();
  });
});
