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
            objeto_alcance: {
              items: [],
              confidence: 0,
              source_references: [],
              extraction_status: "not_found",
              summary: "Sin datos",
              is_reviewed: false,
            },
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
            garantias: {
              items: [],
              confidence: 1,
              source_references: [
                {
                  page: 3,
                  document_id: "doc-1",
                  text_snippet: "No se exige garantía de anticipo.",
                },
              ],
              extraction_status: "not_applicable",
              summary: "No aplica",
              is_reviewed: false,
            },
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
            objeto_alcance: {
              items: [
                {
                  field_name: "Objeto",
                  field_value: "Servicio",
                  field_state: "extraido",
                  confidence: 0.9,
                  citations: [
                    {
                      text: "Texto cita",
                      page: 3,
                      document_id: "doc-1",
                      document_name: "Documento",
                    },
                  ],
                },
              ],
              confidence: 0.9,
              source_references: [],
              extraction_status: "success",
              summary: "Resumen",
              is_reviewed: false,
              narrative: {
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
                    page: 3,
                    text: "Texto cita",
                  },
                ],
              },
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
});
