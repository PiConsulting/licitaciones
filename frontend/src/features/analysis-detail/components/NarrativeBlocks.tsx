import { ChevronDown, Eye } from "lucide-react";
import { useState } from "react";

import type { CategoryNarrative, Citation, NarrativeSource } from "../types";
import { splitLabelAndValue } from "../utils/splitLabelAndValue";
import {
  collectParagraphSourceIds,
  collectReferencedSourceIds,
  filterVerifiedSources,
  resolveSourceIdsToSources,
  sourceToCitation,
} from "../utils/resolveNarrativeSources";
import { SourceEyeButton as EyeButton } from "./SourceEyeButton";

interface NarrativeBlocksProps {
  narrative: CategoryNarrative;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

/** `source_ids` que referencian los bloques `paragraph`.
 *
 * Los párrafos no tienen un "ítem" al que colgarle un botón sin ensuciar la
 * lectura corrida, así que su evidencia sigue yendo al listado del pie. Es el
 * caso de categorías como Objeto y Alcance, que son un párrafo y no una lista.
 */
/** Todos los `source_ids` que efectivamente usa algún bloque/bullet/fila.
 * Una fuente que ningún elemento referencia no puede aparecer en ningún lado:
 * mostrarla sugiere una trazabilidad que no existe. */

/** Título corto + detalle para un bullet. `titulo` es lo esperado (lo sintetiza
 * la síntesis del backend); el split por ":" solo cubre narrativas viejas
 * persistidas antes de que ese campo existiera -- nunca debería ser el camino
 * normal en datos nuevos. Sin ninguno de los dos, el texto completo hace de
 * título para no dejar la fila sin nada que mostrar. */
function resolveTituloYDetalle(item: { titulo?: string; text: string }): { titulo: string; detalle: string } {
  const titulo = item.titulo?.trim();
  if (titulo) {
    return { titulo, detalle: item.text };
  }
  const split = splitLabelAndValue(item.text);
  if (split) {
    return { titulo: split.label, detalle: split.value };
  }
  return { titulo: item.text, detalle: "" };
}

// Porcentaje primero (el dato más habitual en garantías/multas); monto en
// pesos como respaldo cuando no hay porcentaje (ej. "$ 40.000.000").
const PERCENT_RE = /\d+(?:[.,]\d+)?\s?%/;
// El grupo debe terminar en dígito, no en "." ni "," -- si no, un monto al
// final de una oración ("... no supere $ 40.000.000.") arrastraba el punto
// final como si fuera parte del número.
const AMOUNT_RE = /\$\s?\d(?:[\d.,]*\d)?/;

/** El valor cuantificable más relevante del detalle (ej. "4%", "$ 40.000.000"),
 * para mostrar junto al título -- alguien escaneando la lista de garantías
 * quiere ver el porcentaje/monto sin tener que leer cada oración completa.
 * Sin porcentaje ni monto (ej. una garantía técnica, o "formas de
 * constitución" sin cifra propia), no se muestra nada -- nunca se inventa. */
function resolveDetalleHighlight(detalle: string): string | null {
  const percent = detalle.match(PERCENT_RE);
  if (percent) {
    return percent[0].replace(/\s+/g, "");
  }
  const amount = detalle.match(AMOUNT_RE);
  if (amount) {
    return amount[0].replace(/\s+/g, "");
  }
  return null;
}

/**
 * Renderiza la respuesta de experto de una categoría: siempre bloques en
 * lenguaje natural (párrafo/lista/tabla), nunca `field_name: field_value`
 * crudo — ni acá ni en ningún otro lugar de esta vista.
 *
 * Cada párrafo/bullet/fila queda conectado a SUS propias fuentes (no a las de
 * la categoría entera): al abrir el visor sólo viaja la evidencia que respalda
 * ESE elemento puntual.
 *
 * La evidencia se ofrece de dos maneras, según la forma del contenido:
 *
 *   - **bullets y filas de tabla** llevan su propio botón (un ojo discreto al
 *     final de la línea) que abre el PDF en la cita de ese ítem. Un ítem, una
 *     fuente, un click: la persona verifica lo que acaba de leer sin tener que
 *     cruzar una lista de fuentes contra una lista de afirmaciones.
 *   - **párrafos** mantienen el listado "Fuentes verificables" al pie, porque
 *     no hay un ítem discreto donde anclar el botón.
 */
export function NarrativeBlocks({
  narrative,
  onViewSource,
}: NarrativeBlocksProps) {
  const [paragraphSourcesExpanded, setParagraphSourcesExpanded] = useState(false);
  const referencedSourceIds = collectReferencedSourceIds(narrative.blocks);
  const paragraphSourceIds = collectParagraphSourceIds(narrative.blocks);

  const verifiedSources = filterVerifiedSources(narrative.sources).filter((source) =>
    referencedSourceIds.has(source.id),
  );
  const sourceById = new Map(verifiedSources.map((source) => [source.id, source]));

  // Sólo la evidencia de los párrafos va al listado del pie; la de los ítems vive en el ojo de cada ítem.
  const paragraphSources = verifiedSources.filter((source) => paragraphSourceIds.has(source.id));
  const paragraphCitations = paragraphSources.map(sourceToCitation);

  const resolveSources = (sourceIds: number[]): NarrativeSource[] =>
    resolveSourceIdsToSources(sourceIds, sourceById);

  /** Abre el visor acotado a la evidencia del elemento clickeado: la
   * navegación anterior/siguiente del visor recorre SÓLO esas citas, no las de
   * toda la categoría. */
  const handleViewElementSource = (sourceIds: number[]) => {
    const sources = resolveSources(sourceIds);
    if (!onViewSource || sources.length === 0) {
      return;
    }
    const citations = sources.map(sourceToCitation);
    onViewSource({ citation: citations[0], citations, sources });
  };

  const handleViewParagraphSource = (sourceId: number) => {
    const source = sourceById.get(sourceId);
    if (!onViewSource || !source) {
      return;
    }
    onViewSource({
      citation: sourceToCitation(source),
      citations: paragraphCitations,
      sources: paragraphSources,
    });
  };

  /** Ver `SourceEyeButton`: el ojo sólo aparece si el ítem tiene al menos una
   * fuente verificable. Un botón que no lleva a ningún lado es peor que
   * ninguno. */
  function SourceEyeButton({ sourceIds }: { sourceIds: number[] }) {
    const sources = resolveSources(sourceIds);
    if (sources.length === 0) {
      return null;
    }
    return (
      <EyeButton
        pages={sources.map((source) => source.page)}
        onClick={() => handleViewElementSource(sourceIds)}
      />
    );
  }

  return (
    <section className="p-0" data-testid="narrative-blocks">
      <div className="space-y-3">
        {narrative.blocks.map((block, index) => {
          if (block.type === "paragraph") {
            return (
              <div key={index} className="flex items-start gap-2" data-testid="narrative-paragraph">
                <p className="flex-1 text-sm leading-relaxed text-[#003C6B]">
                  {block.text}
                </p>
              </div>
            );
          }

          if (block.type === "bullet_list") {
            return (
              <div key={index} data-testid="narrative-bullet-list">
                <ul className="divide-y divide-[rgba(0,60,107,.06)]">
                  {block.items.map((item, itemIndex) => {
                    const { titulo, detalle } = resolveTituloYDetalle(item);
                    const highlight = detalle ? resolveDetalleHighlight(detalle) : null;

                    return (
                      <li
                        key={itemIndex}
                        className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0"
                        data-testid="narrative-bullet-item"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-[#003C6B]">{titulo}</span>
                          {highlight ? (
                            <>
                              <span className="text-3xl leading-none text-[rgba(0,60,107,.35)]" aria-hidden="true">
                                •
                              </span>
                              <span
                                className="text-sm font-bold text-[rgba(0,60,107,.85)]"
                                data-testid="narrative-bullet-highlight"
                              >
                                {highlight}
                              </span>
                            </>
                          ) : null}
                          <SourceEyeButton sourceIds={item.source_ids} />
                        </div>
                        {detalle ? (
                          <p className="text-[13px] leading-relaxed text-[rgba(0,60,107,.68)]">{detalle}</p>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          }

          return (
            <div key={index} className="overflow-x-auto" data-testid="narrative-table">
              <table className="w-full min-w-full border-collapse text-left text-sm">
                <thead>
                  <tr>
                    {block.headers.map((header, headerIndex) => (
                      <th key={headerIndex} className="border-b border-[rgba(0,60,107,.12)] px-2 py-1 font-semibold text-[rgba(0,60,107,.68)]">
                        {header}
                      </th>
                    ))}
                    <th className="border-b border-[rgba(0,60,107,.12)] px-2 py-1" aria-hidden="true" />
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className="border-b border-[rgba(0,60,107,.08)]">
                      {row.cells.map((cell, cellIndex) => (
                        <td key={cellIndex} className="px-2 py-1.5 text-[#003C6B]">
                          {cell}
                        </td>
                      ))}
                      <td className="px-2 py-1.5 align-top">
                        <div className="flex items-center justify-end gap-2">
                          <SourceEyeButton sourceIds={row.source_ids} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>

      {paragraphSources.length > 0 ? (
        <div className="mt-2" data-testid="category-sources">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 text-left"
            aria-expanded={paragraphSourcesExpanded}
            data-testid="paragraph-sources-toggle"
            onClick={() => setParagraphSourcesExpanded((prev) => !prev)}
          >
            <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[rgba(0,60,107,.68)]">
              Fuentes verificables
            </span>
            <span className="inline-flex h-5 w-5 items-center justify-center text-[#003C6B]">
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${paragraphSourcesExpanded ? "rotate-180" : "rotate-0"}`}
                aria-hidden="true"
              />
            </span>
          </button>

          {paragraphSourcesExpanded ? (
            <ul className="mt-2 flex flex-wrap gap-2" data-testid="category-sources-list">
              {paragraphSources.map((source) => (
                <li key={source.id}>
                  <button
                    type="button"
                    className="inline-flex h-7 items-center gap-1.5 rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2.5 text-xs font-semibold text-[#0099DB] transition-colors hover:border-[#0099DB]"
                    onClick={() => handleViewParagraphSource(source.id)}
                  >
                    <Eye className="h-3 w-3" aria-hidden="true" />
                    <span className="font-semibold">{source.document_name}</span>
                    <span>{` · pág. ${source.page}`}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {verifiedSources.length === 0 ? (
        <p className="mt-3 text-xs text-[rgba(0,60,107,.55)]" data-testid="category-sources-empty">
          Sin evidencia clickeable para esta categoría. No puede marcarse como revisada automáticamente.
        </p>
      ) : null}
    </section>
  );
}
