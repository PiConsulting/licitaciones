/**
 * El mapper de la API tiene que conservar `highlight_regions`.
 *
 * `toNarrativeSource` no las copiaba, y es el ÚNICO constructor de
 * `NarrativeSource` del frontend. O sea que `getCombinedHighlightRegions()`
 * devolvía siempre `[]`, `useCoordinateHighlight` era siempre `false`, y el
 * visor caía siempre al resaltado heurístico por texto — que marca spans
 * enteros y por eso se veía "resaltado por párrafo".
 *
 * El camino de coordenadas era código muerto en producción. Por eso varias
 * correcciones del cálculo de coordenadas en el backend no cambiaron nada de lo
 * que se veía en pantalla: los números llegaban bien hasta el borde de la API y
 * se descartaban en esta función.
 *
 * Ningún test lo detectaba: el del visor mockea la respuesta YA mapeada, y el
 * del overlay construye las regiones a mano. Este test cubre justo la costura
 * que quedaba sin cubrir — de la respuesta HTTP cruda al objeto tipado.
 */

import { beforeEach, describe, expect, test, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock("../../api/client", () => ({ default: { get: getMock } }));

import { getAnalysisById } from "./analysisApi";

const REGION = { x: 56.8, y: 465.2, width: 240.34, height: 10 };

function respuestaConNarrativa(sources: unknown[]) {
  return {
    data: {
      id: "analysis-1",
      created_at: "2026-08-14T00:00:00Z",
      status: "analyzed",
      current_stage: "completed",
      current_version: {
        id: "v1",
        version_number: 1,
        extracted_data: {
          objeto_alcance: [
            {
              confidence: 0.9,
              extraction_status: "success",
              tipo: "resumen_objeto",
              valor: "Adquisición de servidores",
              source_references: [
                {
                  document_id: "doc-1",
                  page_number: 3,
                  citation: "Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN",
                },
              ],
            },
          ],
          objeto_alcance_extraction_status: "success",
          objeto_alcance_narrative: {
            blocks: [
              {
                type: "paragraph",
                text: "Se licita la adquisición de servidores.",
                confidence_level: "alta",
                source_ids: [0],
              },
            ],
            sources,
          },
        },
        conflicts: {},
        created_at: "2026-08-14T00:00:00Z",
      },
      documents: [],
    },
  };
}

const SOURCE_BASE = {
  id: 0,
  document_id: "doc-1",
  page_number: 3,
  citation: "Item 1: 4 (cuatro) Servidores de aplicaciones tipo XEN",
  unverified: false,
};

async function primeraSource(sources: unknown[]) {
  getMock.mockReset();
  getMock.mockResolvedValueOnce(respuestaConNarrativa(sources));
  const result = await getAnalysisById("analysis-1");
  return result.current_version.extracted_data.objeto_alcance.narrative?.sources[0];
}

describe("toNarrativeSource conserva las coordenadas del backend", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  test("las regiones llegan tal cual al objeto tipado", async () => {
    const source = await primeraSource([{ ...SOURCE_BASE, highlight_regions: [REGION] }]);

    expect(source?.highlight_regions).toEqual([REGION]);
  });

  test("varias regiones (una cita que ocupa dos renglones) llegan todas", async () => {
    const otra = { x: 56.8, y: 476.7, width: 120, height: 10 };
    const source = await primeraSource([
      { ...SOURCE_BASE, highlight_regions: [REGION, otra] },
    ]);

    expect(source?.highlight_regions).toHaveLength(2);
  });

  test("sin regiones queda un array vacío, nunca undefined", async () => {
    const source = await primeraSource([SOURCE_BASE]);

    expect(source?.highlight_regions).toEqual([]);
  });

  test("una región malformada se descarta sin tirar abajo la fuente", async () => {
    const source = await primeraSource([
      {
        ...SOURCE_BASE,
        highlight_regions: [REGION, { x: "no es un número", y: 1, width: 2, height: 3 }, null],
      },
    ]);

    expect(source?.highlight_regions).toEqual([REGION]);
    expect(source?.text).toBe(SOURCE_BASE.citation);
  });

  test("el resto de los campos de la fuente sigue mapeándose igual", async () => {
    const source = await primeraSource([{ ...SOURCE_BASE, highlight_regions: [REGION] }]);

    expect(source?.document_id).toBe("doc-1");
    expect(source?.page).toBe(3);
    expect(source?.text).toBe(SOURCE_BASE.citation);
    expect(source?.unverified).toBe(false);
  });
});
