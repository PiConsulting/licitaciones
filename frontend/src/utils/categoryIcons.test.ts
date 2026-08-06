import { describe, it, expect } from "vitest";
import { CATEGORY_ORDER, CRITICAL_CATEGORIES } from "./categoryIcons";
import type { CategoryId } from "../features/analysis-detail/types";

describe("categoryIcons", () => {
  describe("CATEGORY_ORDER", () => {
    it("debe tener exactamente 7 categorías (sin datos_procedimiento)", () => {
      expect(CATEGORY_ORDER).toHaveLength(7);
    });

    it("debe seguir el orden canónico de negocio", () => {
      const expectedOrder: CategoryId[] = [
        "objeto_alcance",
        "requisitos_admisibilidad",
        "garantias",
        "plazos_clave",
        "criterios_evaluacion",
        "causales_rechazo",
        "anexos_obligatorios",
      ];

      expect(CATEGORY_ORDER).toEqual(expectedOrder);
    });

    it("NO debe incluir datos_procedimiento en el checklist principal", () => {
      expect(CATEGORY_ORDER).not.toContain("datos_procedimiento");
    });

    it("debe incluir todas las categorías canónicas", () => {
      expect(CATEGORY_ORDER).toContain("objeto_alcance");
      expect(CATEGORY_ORDER).toContain("requisitos_admisibilidad");
      expect(CATEGORY_ORDER).toContain("garantias");
      expect(CATEGORY_ORDER).toContain("plazos_clave");
      expect(CATEGORY_ORDER).toContain("criterios_evaluacion");
      expect(CATEGORY_ORDER).toContain("causales_rechazo");
      expect(CATEGORY_ORDER).toContain("anexos_obligatorios");
    });
  });

  describe("CRITICAL_CATEGORIES", () => {
    it("debe mantener las categorías críticas para reglas de validación", () => {
      expect(CRITICAL_CATEGORIES.has("plazos_clave")).toBe(true);
      expect(CRITICAL_CATEGORIES.has("garantias")).toBe(true);
      expect(CRITICAL_CATEGORIES.has("causales_rechazo")).toBe(true);
    });

    it("NO debe afectar el orden visual (es solo para criticidad)", () => {
      // Las categorías críticas pueden aparecer en cualquier posición del CATEGORY_ORDER
      // Este test verifica que la criticidad no está acoplada al orden
      const criticalIndices = Array.from(CRITICAL_CATEGORIES).map((cat) =>
        CATEGORY_ORDER.indexOf(cat),
      );

      // Verificar que las categorías críticas NO están todas al inicio
      const areAllAtStart = criticalIndices.every((idx) => idx < 3);
      expect(areAllAtStart).toBe(false);
    });
  });
});
