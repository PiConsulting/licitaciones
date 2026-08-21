/**
 * CTX-03: "no analizado" no es "no encontrado".
 *
 * Cuatro campos del contrato (`documentos_requeridos`,
 * `restricciones_participacion`, `cronograma_proceso`, `estimacion_presupuesto`)
 * están hardcodeados a vacío en el backend, y ningún nodo del grafo los
 * completa. Estaban en `not_found`, que en toda esta vista significa "el pliego
 * no lo dice" -- una afirmación sobre el pliego que el sistema nunca verificó.
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

  test("una categoría realmente vacía no dice 'no analizada'", () => {
    render(<CategorySection category={categoria("not_found")} categoryId="datos_procedimiento" />);

    expect(screen.queryByText(/NO ANALIZADA/i)).not.toBeInTheDocument();
  });

  test("el estado nuevo no se confunde con 'no aplica'", () => {
    render(<CategorySection category={categoria("not_analyzed")} categoryId="datos_procedimiento" />);

    expect(screen.queryByText(/^NO APLICA$/i)).not.toBeInTheDocument();
  });
});
