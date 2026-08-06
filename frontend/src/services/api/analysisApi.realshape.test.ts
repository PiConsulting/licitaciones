import { beforeEach, describe, expect, test, vi } from "vitest";

// Payload real capturado desde Cosmos (analysis_version.extracted_data).
import REAL_EXTRACTED_DATA from "./__fixtures__/extracted_data.real.json";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  default: {
    get: getMock,
  },
}));

import { getAnalysisById } from "./analysisApi";

describe("normalizeCategories con la forma real del backend", () => {
  beforeEach(() => {
    getMock.mockReset();
    getMock.mockResolvedValueOnce({
      data: {
        id: "analysis-real",
        created_at: "2026-08-05T00:00:00Z",
        status: "analyzed",
        current_stage: "completed",
        current_version: {
          id: "v1",
          version_number: 1,
          extracted_data: REAL_EXTRACTED_DATA,
          conflicts: {},
          created_at: "2026-08-05T00:00:00Z",
        },
        documents: [],
      },
    });
  });

  test("todas las categorías de la UI reciben ítems", async () => {
    const result = await getAnalysisById("analysis-real");
    const data = result.current_version.extracted_data;

    // Solo las 7 categorías canónicas (sin datos_procedimiento)
    for (const categoryId of [
      "objeto_alcance",
      "requisitos_admisibilidad",
      "garantias",
      "plazos_clave",
      "criterios_evaluacion",
      "causales_rechazo",
      "anexos_obligatorios",
    ] as const) {
      expect(data[categoryId].items.length, `categoría ${categoryId}`).toBeGreaterThan(0);
      expect(data[categoryId].extraction_status, `categoría ${categoryId}`).toBe("success");
    }
  });

  test("datos_procedimiento NO está en las categorías procesadas", async () => {
    const result = await getAnalysisById("analysis-real");
    const data = result.current_version.extracted_data;

    // datos_procedimiento no debe estar en el objeto normalizado
    expect(data.datos_procedimiento).toBeUndefined();
  });

  test("los ítems traen nombre, valor y cita utilizables", async () => {
    const result = await getAnalysisById("analysis-real");
    const objeto = result.current_version.extracted_data.objeto_alcance;

    const resumen = objeto.items.find((item) => item.field_name === "Objeto");
    expect(resumen).toBeDefined();
    expect(resumen?.field_value).toBeTruthy();
    expect(resumen?.field_state).toBe("extraido");
    expect(resumen?.confidence).toBeGreaterThan(0);
    expect(resumen?.citations[0]?.text.length).toBeGreaterThan(20);
    expect(resumen?.citations[0]?.page).toBeGreaterThan(0);
    expect(resumen?.citations[0]?.document_id).toBeTruthy();
  });

  test("los plazos derivan valor desde fecha/hora, no desde `valor`", async () => {
    const result = await getAnalysisById("analysis-real");
    const plazos = result.current_version.extracted_data.plazos_clave;

    expect(plazos.items.every((item) => item.field_name !== "Campo sin nombre")).toBe(true);
    expect(plazos.items.some((item) => item.field_value != null)).toBe(true);
  });

  test("la categoría expone confianza y referencias agregadas", async () => {
    const result = await getAnalysisById("analysis-real");
    const garantias = result.current_version.extracted_data.garantias;

    expect(garantias.confidence).toBeGreaterThan(0);
    expect(garantias.source_references.length).toBeGreaterThan(0);
    expect(garantias.summary).not.toBe("Sin resumen disponible.");
  });
});
