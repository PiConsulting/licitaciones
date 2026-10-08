import { beforeEach, describe, expect, test, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  default: {
    get: getMock,
  },
}));

import { getAnalysisById } from "./analysisApi";

describe("analysisApi extraction_status parsing", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  test("preserva extraction_status=not_found del backend", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        id: "analysis-1",
        created_at: "2026-08-05T00:00:00Z",
        status: "analyzed",
        current_stage: "completed",
        current_version: {
          id: "v1",
          version_number: 1,
          extracted_data: {
            objeto_alcance: [],
            objeto_alcance_extraction_status: "not_found",
          },
          conflicts: {},
          created_at: "2026-08-05T00:00:00Z",
        },
        documents: [],
      },
    });

    const result = await getAnalysisById("analysis-1");
    expect(result.current_version.extracted_data.objeto_alcance.extraction_status).toBe("not_found");
  });

  test("preserva extraction_status=not_applicable del backend", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        id: "analysis-2",
        created_at: "2026-08-05T00:00:00Z",
        status: "analyzed",
        current_stage: "completed",
        current_version: {
          id: "v1",
          version_number: 1,
          extracted_data: {
            garantias: [],
            garantias_extraction_status: "not_applicable",
          },
          conflicts: {},
          created_at: "2026-08-05T00:00:00Z",
        },
        documents: [],
      },
    });

    const result = await getAnalysisById("analysis-2");
    expect(result.current_version.extracted_data.garantias.extraction_status).toBe("not_applicable");
  });

  test("hidrata document_name con filename real cuando llega como 'Documento'", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        id: "analysis-3",
        created_at: "2026-08-05T00:00:00Z",
        status: "analyzed",
        current_stage: "completed",
        current_version: {
          id: "v1",
          version_number: 1,
          extracted_data: {
            objeto_alcance: [
              {
                tipo: "resumen_objeto",
                valor: "Servicio",
                confidence: 0.9,
                extraction_status: "success",
                source_references: [
                  {
                    document_id: "doc-1",
                    page_number: 3,
                    citation: "Texto cita",
                  },
                ],
              },
            ],
            objeto_alcance_extraction_status: "success",
            objeto_alcance_narrative: {
              blocks: [
                {
                  type: "paragraph",
                  text: "Servicio requerido.",
                  confidence_level: "high",
                  source_ids: [0],
                },
              ],
              sources: [
                {
                  id: 0,
                  document_id: "doc-1",
                  document_name: "Documento",
                  page_number: 3,
                  citation: "Texto cita",
                },
              ],
            },
          },
          conflicts: {},
          created_at: "2026-08-05T00:00:00Z",
        },
        documents: [{ id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true }],
      },
    });

    const result = await getAnalysisById("analysis-3");
    const category = result.current_version.extracted_data.objeto_alcance;

    expect(category.items[0]?.citations[0]?.document_name).toBe("Pliego Principal.pdf");
    expect(category.narrative?.sources[0]?.document_name).toBe("Pliego Principal.pdf");
  });

  test("preserva `resumen` de cada bullet de preview_criterios_narrative (regresión: cards de preview en '-')", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        id: "analysis-4",
        created_at: "2026-09-16T00:00:00Z",
        status: "analyzed",
        current_stage: "completed",
        current_version: {
          id: "v1",
          version_number: 1,
          extracted_data: {
            preview_criterios: [],
            preview_criterios_extraction_status: "success",
            preview_criterios_narrative: {
              blocks: [
                {
                  type: "bullet_list",
                  items: [
                    {
                      text: "Mantenimiento de oferta: 60 días",
                      resumen: "60 días",
                      confidence_level: "high",
                      source_ids: [0],
                    },
                  ],
                },
              ],
              sources: [
                {
                  id: 0,
                  document_id: "doc-1",
                  document_name: "Pliego Principal.pdf",
                  page_number: 3,
                  citation: "La oferta deberá mantenerse por 60 días.",
                },
              ],
            },
          },
          conflicts: {},
          created_at: "2026-09-16T00:00:00Z",
        },
        documents: [{ id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true }],
      },
    });

    const result = await getAnalysisById("analysis-4");
    const category = result.current_version.extracted_data.preview_criterios;
    const block = category?.narrative?.blocks[0];

    expect(block?.type).toBe("bullet_list");
    if (block?.type === "bullet_list") {
      expect(block.items[0]?.resumen).toBe("60 días");
    }
  });

  test("preserva `titulo` de cada bullet de una narrativa (bug real: se descartaba en el parseo, todas las categorías caían siempre a la fila sin título)", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        id: "analysis-5",
        created_at: "2026-09-28T00:00:00Z",
        status: "analyzed",
        current_stage: "completed",
        current_version: {
          id: "v1",
          version_number: 1,
          extracted_data: {
            requisitos_admisibilidad: [],
            requisitos_admisibilidad_extraction_status: "success",
            requisitos_admisibilidad_narrative: {
              blocks: [
                {
                  type: "bullet_list",
                  items: [
                    {
                      text: "Presentar constancia vigente al momento de la apertura.",
                      titulo: "Constancia RUP vigente",
                      confidence_level: "high",
                      source_ids: [0],
                    },
                  ],
                },
              ],
              sources: [
                {
                  id: 0,
                  document_id: "doc-1",
                  document_name: "Pliego Principal.pdf",
                  page_number: 3,
                  citation: "Constancia RUP vigente al momento de la apertura.",
                },
              ],
            },
          },
          conflicts: {},
          created_at: "2026-09-28T00:00:00Z",
        },
        documents: [{ id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true }],
      },
    });

    const result = await getAnalysisById("analysis-5");
    const category = result.current_version.extracted_data.requisitos_admisibilidad;
    const block = category?.narrative?.blocks[0];

    expect(block?.type).toBe("bullet_list");
    if (block?.type === "bullet_list") {
      expect(block.items[0]?.titulo).toBe("Constancia RUP vigente");
    }
  });
});
