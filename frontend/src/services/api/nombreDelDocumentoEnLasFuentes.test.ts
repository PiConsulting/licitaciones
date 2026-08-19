/**
 * CTX-06: la lista "Fuentes verificables" decía "Documento" para todas.
 *
 * `NarrativeBlocks.tsx` renderiza `{source.document_name} · pág. {source.page}`,
 * y `document_name` era la constante `"Documento"` en los tres mappers que
 * construyen fuentes en `analysisApi.ts`. Con un solo documento eso era
 * simplemente inútil. En el análisis de Santa Fe (`18a86363-…`: un pliego y
 * cuatro anexos) las fuentes de una misma categoría se leen todas igual:
 *
 *     Documento · pág. 1
 *     Documento · pág. 1
 *
 * y esas dos son la página 1 de dos archivos distintos.
 *
 * El backend ahora manda `filename` en cada referencia (antes llegaba en `null`
 * en las 20 referencias de esa corrida: el campo existía y nadie lo escribía).
 */

import { beforeEach, describe, expect, test, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("../../api/client", () => ({ default: { get: getMock } }));

import { getAnalysisById } from "./analysisApi";

const PLIEGO = "ebe9dca5-ba5d-432f-a658-8d7026974e8b";
const ANEXO_IV = "c7ebfe58-c452-414a-a213-4c14410c6330";

function respuestaCon(extractedData: unknown) {
  return {
    data: {
      id: "18a86363-39ac-4b52-a2e2-1b1146b89ff8",
      created_at: "2026-08-19T15:29:05Z",
      status: "analyzed",
      current_stage: "completed",
      current_version: {
        id: "v1",
        version_number: 1,
        extracted_data: extractedData,
        conflicts: [],
        created_at: "2026-08-19T15:39:50Z",
      },
      documents: [
        { id: PLIEGO, filename: "Pliego - Santa Fe.pdf", page_count: 2, is_primary: true },
        { id: ANEXO_IV, filename: "ANEXO IV - Santa Fe.pdf", page_count: 1, is_primary: false },
      ],
    },
  };
}

/** Una categoría con narrativa y dos fuentes de la misma página de dos
 * documentos distintos, con la forma exacta que emite el backend. */
function categoriaConDosFuentes(conFilename: boolean) {
  const nombre = (n: string) => (conFilename ? { filename: n } : {});
  return {
    requisitos_admisibilidad: [
      {
        confidence: 0.7,
        extraction_status: "success",
        tipo: "capacidad_minima",
        valor: "antigüedad mínima de dos (2) años",
        source_references: [
          {
            document_id: ANEXO_IV,
            page_number: 1,
            citation: "debiendo el oferente contar con una antigüedad mínima de dos (2) años",
            ...nombre("ANEXO IV - Santa Fe.pdf"),
          },
        ],
      },
    ],
    requisitos_admisibilidad_narrative: {
      blocks: [
        {
          type: "paragraph",
          text: "El oferente debe acreditar dos años de antigüedad.",
          confidence_level: "media",
          source_ids: [0, 1],
        },
      ],
      sources: [
        {
          id: 0,
          document_id: PLIEGO,
          page_number: 1,
          citation: "OBJETO: ADQUISICIÓN DE UN SISTEMA DE ALMACENAMIENTO DE DATOS",
          ...nombre("Pliego - Santa Fe.pdf"),
        },
        {
          id: 1,
          document_id: ANEXO_IV,
          page_number: 1,
          citation: "debiendo el oferente contar con una antigüedad mínima de dos (2) años",
          ...nombre("ANEXO IV - Santa Fe.pdf"),
        },
      ],
    },
  };
}

describe("CTX-06 · el nombre del documento en las fuentes", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  test("cada fuente muestra el archivo del que salió, no 'Documento'", async () => {
    getMock.mockResolvedValueOnce(respuestaCon(categoriaConDosFuentes(true)));

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const narrative = result.current_version.extracted_data.requisitos_admisibilidad.narrative;

    expect(narrative?.sources.map((s) => s.document_name)).toEqual([
      "Pliego - Santa Fe.pdf",
      "ANEXO IV - Santa Fe.pdf",
    ]);
  });

  test("dos fuentes de la misma página ya no se leen igual", async () => {
    getMock.mockResolvedValueOnce(respuestaCon(categoriaConDosFuentes(true)));

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const narrative = result.current_version.extracted_data.requisitos_admisibilidad.narrative;

    // Exactamente el renglón que arma NarrativeBlocks.tsx.
    const renglones = (narrative?.sources ?? []).map((s) => `${s.document_name} · pág. ${s.page}`);
    expect(new Set(renglones).size).toBe(2);
    expect(renglones).toEqual([
      "Pliego - Santa Fe.pdf · pág. 1",
      "ANEXO IV - Santa Fe.pdf · pág. 1",
    ]);
  });

  test("sin filename se conserva el default y no se rompe nada", async () => {
    // Un análisis viejo, ya persistido antes de este fix.
    getMock.mockResolvedValueOnce(respuestaCon(categoriaConDosFuentes(false)));

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const narrative = result.current_version.extracted_data.requisitos_admisibilidad.narrative;

    expect(narrative?.sources.map((s) => s.document_name)).toEqual(["Documento", "Documento"]);
    expect(narrative?.sources).toHaveLength(2);
  });

  test("un filename vacío o en blanco cae al default", async () => {
    const datos = categoriaConDosFuentes(true) as Record<string, any>;
    datos.requisitos_admisibilidad_narrative.sources[0].filename = "   ";
    getMock.mockResolvedValueOnce(respuestaCon(datos));

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const narrative = result.current_version.extracted_data.requisitos_admisibilidad.narrative;

    expect(narrative?.sources[0].document_name).toBe("Documento");
    expect(narrative?.sources[1].document_name).toBe("ANEXO IV - Santa Fe.pdf");
  });

  test("el document_id sigue viajando: de ahí sale el resaltado", async () => {
    getMock.mockResolvedValueOnce(respuestaCon(categoriaConDosFuentes(true)));

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const narrative = result.current_version.extracted_data.requisitos_admisibilidad.narrative;

    expect(narrative?.sources.map((s) => s.document_id)).toEqual([PLIEGO, ANEXO_IV]);
  });

  test("las citations de los ítems también dicen el archivo", async () => {
    getMock.mockResolvedValueOnce(respuestaCon(categoriaConDosFuentes(true)));

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const items = result.current_version.extracted_data.requisitos_admisibilidad.items;

    expect(items[0].citations[0].document_name).toBe("ANEXO IV - Santa Fe.pdf");
  });

  test("los plazos, que tienen su propio mapper, también", async () => {
    getMock.mockResolvedValueOnce(
      respuestaCon({
        plazos_clave: [
          {
            confidence: 0.7,
            extraction_status: "success",
            tipo: "plazo_ejecucion",
            expresion_relativa: "quince (15) días corridos",
            texto_original: "la Provincia dispondrá de un plazo máximo de quince (15) días corridos",
            source_references: [
              {
                document_id: ANEXO_IV,
                page_number: 3,
                citation: "la Provincia dispondrá de un plazo máximo de quince (15) días corridos",
                filename: "ANEXO IV - Santa Fe.pdf",
              },
            ],
          },
        ],
      }),
    );

    const result = await getAnalysisById("18a86363-39ac-4b52-a2e2-1b1146b89ff8");
    const items = result.current_version.extracted_data.plazos_clave.items;

    expect(items[0].citations[0].document_name).toBe("ANEXO IV - Santa Fe.pdf");
  });
});
