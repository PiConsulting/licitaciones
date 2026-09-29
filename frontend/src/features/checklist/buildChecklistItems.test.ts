import { describe, expect, test } from "vitest";

import { buildChecklistItemContents } from "./buildChecklistItems";
import type { CategoryData } from "../analysis-detail/types";
import type { TrackingItem } from "../../types/tracking";

function trackingItem(overrides: Partial<TrackingItem> & { id: string }): TrackingItem {
  return {
    tracking_item_id: overrides.id,
    category_key: "requisitos_admisibilidad",
    status: "not_evaluated",
    source_item_ref: {
      version_id: "v1",
      field_name: "documento",
      document_id: "doc-1",
      page: 3,
      citation_hash: null,
      ...overrides.source_item_ref,
    },
    ...overrides,
  };
}

describe("buildChecklistItemContents", () => {
  test("caso normal: un tracking item por bullet, emparejados por posición", () => {
    const category: CategoryData = {
      items: [],
      confidence: 0,
      source_references: [],
      extraction_status: "success",
      summary: "",
      is_reviewed: false,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              { titulo: "Inscripción vigente", text: "Presentar constancia.", confidence_level: "high", source_ids: [0] },
              { titulo: "Garantía de oferta", text: "Acompañar la garantía.", confidence_level: "high", source_ids: [1] },
            ],
          },
        ],
        sources: [
          { id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 3, text: "constancia" },
          { id: 1, document_id: "doc-1", document_name: "Pliego.pdf", page: 4, text: "garantía" },
        ],
      },
    };
    const items = [
      trackingItem({ id: "a", source_item_ref: { version_id: "v1", field_name: "documento", document_id: "doc-1", page: 3, citation_hash: null } }),
      trackingItem({ id: "b", source_item_ref: { version_id: "v1", field_name: "documento", document_id: "doc-1", page: 4, citation_hash: null } }),
    ];

    const result = buildChecklistItemContents(category, "requisitos_admisibilidad", items);

    expect(result[0].label).toBe("Inscripción vigente");
    expect(result[1].label).toBe("Garantía de oferta");
  });

  test("la síntesis consolidó 2 items crudos en 1 bullet: el tracking item sobrante se resuelve por (documento, página), no queda como 'documento' a secas", () => {
    // Caso real reportado (dd0bdcd0): 8 items crudos, la síntesis los consolidó en 7 bullets.
    const category: CategoryData = {
      items: [],
      confidence: 0,
      source_references: [],
      extraction_status: "success",
      summary: "",
      is_reviewed: false,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                titulo: "Libre deuda alimentaria",
                text: "Presentar certificado de libre deuda registrada o la autorización (Anexo II).",
                confidence_level: "high",
                source_ids: [0, 1],
              },
            ],
          },
        ],
        sources: [
          { id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 5, text: "libre deuda registrada" },
          { id: 1, document_id: "doc-1", document_name: "Pliego.pdf", page: 6, text: "autorización Anexo II" },
        ],
      },
    };
    // 2 tracking items (creados de los 2 items crudos originales) para 1 solo bullet consolidado.
    const items = [
      trackingItem({ id: "libre-deuda", source_item_ref: { version_id: "v1", field_name: "documento", document_id: "doc-1", page: 5, citation_hash: null } }),
      trackingItem({ id: "anexo-ii", source_item_ref: { version_id: "v1", field_name: "documento", document_id: "doc-1", page: 6, citation_hash: null } }),
    ];

    const result = buildChecklistItemContents(category, "requisitos_admisibilidad", items);

    // El primero empareja por posición (índice 0 existe); el segundo, sin bullet en esa posición, se recupera por (documento, página).
    expect(result[0].label).toBe("Libre deuda alimentaria");
    expect(result[1].label).toBe("Libre deuda alimentaria");
    expect(result[1].label).not.toBe("documento");
  });

  test("sin match por posición ni por (documento, página), cae al tipo crudo (nunca deja la fila sin nada)", () => {
    const category: CategoryData = {
      items: [],
      confidence: 0,
      source_references: [],
      extraction_status: "success",
      summary: "",
      is_reviewed: false,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [{ titulo: "Único requisito", text: "Detalle.", confidence_level: "high", source_ids: [0] }],
          },
        ],
        sources: [{ id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 2, text: "detalle" }],
      },
    };
    const items = [
      trackingItem({ id: "a", source_item_ref: { version_id: "v1", field_name: "documento", document_id: "doc-1", page: 2, citation_hash: null } }),
      trackingItem({
        id: "b",
        source_item_ref: { version_id: "v1", field_name: "inscripcion_registro", document_id: "doc-9", page: 40, citation_hash: null },
      }),
    ];

    const result = buildChecklistItemContents(category, "requisitos_admisibilidad", items);

    expect(result[1].label).toBe("inscripcion_registro");
    expect(result[1].text).toBe("");
  });
});
