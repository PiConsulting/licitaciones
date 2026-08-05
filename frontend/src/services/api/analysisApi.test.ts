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
});
