import type { CategoryNarrative, Citation, NarrativeSource } from "../types";
import { SourceEyeButton as EyeButton } from "./SourceEyeButton";

interface NarrativeBlocksProps {
  narrative: CategoryNarrative;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

function sourceToCitation(source: NarrativeSource): Citation {
  return {
    text: source.text,
    page: source.page,
    document_id: source.document_id,
    document_name: source.document_name,
  };
}

/**
 * Filtra sources que no son verificables (marcadas por el backend con
 * `unverified: true`). Estas citations no pueden ser encontradas en el PDF y
 * no deben mostrarse al usuario.
 */
function filterVerifiedSources(sources: NarrativeSource[]): NarrativeSource[] {
  return sources.filter((source) => !source.unverified);
}

/** `source_ids` que referencian los bloques `paragraph`.
 *
 * Los párrafos no tienen un "ítem" al que colgarle un botón sin ensuciar la
 * lectura corrida, así que su evidencia sigue yendo al listado del pie. Es el
 * caso de categorías como Objeto y Alcance, que son un párrafo y no una lista.
 */
function collectParagraphSourceIds(narrative: CategoryNarrative): Set<number> {
  const ids = new Set<number>();
  for (const block of narrative.blocks) {
    if (block.type === "paragraph") {
      block.source_ids.forEach((id) => ids.add(id));
    }
  }
  return ids;
}

/** Todos los `source_ids` que efectivamente usa algún bloque/bullet/fila.
 * Una fuente que ningún elemento referencia no puede aparecer en ningún lado:
 * mostrarla sugiere una trazabilidad que no existe. */
function collectReferencedSourceIds(narrative: CategoryNarrative): Set<number> {
  const ids = new Set<number>();
  for (const block of narrative.blocks) {
    if (block.type === "paragraph") {
      block.source_ids.forEach((id) => ids.add(id));
    } else if (block.type === "bullet_list") {
      block.items.forEach((item) => item.source_ids.forEach((id) => ids.add(id)));
    } else {
      block.rows.forEach((row) => row.source_ids.forEach((id) => ids.add(id)));
    }
  }
  return ids;
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
export function NarrativeBlocks({ narrative, onViewSource }: NarrativeBlocksProps) {
  const referencedSourceIds = collectReferencedSourceIds(narrative);
  const paragraphSourceIds = collectParagraphSourceIds(narrative);

  const verifiedSources = filterVerifiedSources(narrative.sources).filter((source) =>
    referencedSourceIds.has(source.id),
  );
  const sourceById = new Map(verifiedSources.map((source) => [source.id, source]));

  // Sólo la evidencia de los párrafos va al listado del pie. La de los ítems
  // vive en el ojo de cada ítem.
  const paragraphSources = verifiedSources.filter((source) => paragraphSourceIds.has(source.id));
  const paragraphCitations = paragraphSources.map(sourceToCitation);

  const resolveSources = (sourceIds: number[]): NarrativeSource[] =>
    sourceIds
      .map((id) => sourceById.get(id))
      .filter((source): source is NarrativeSource => source !== undefined);

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
    <section className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3" data-testid="narrative-blocks">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Respuesta</h4>

      <div className="mt-2 space-y-3">
        {narrative.blocks.map((block, index) => {
          if (block.type === "paragraph") {
            return (
              <p key={index} className="text-sm leading-relaxed text-gray-800" data-testid="narrative-paragraph">
                {block.text}
              </p>
            );
          }

          if (block.type === "bullet_list") {
            return (
              <ul key={index} className="space-y-1.5" data-testid="narrative-bullet-list">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="flex items-start gap-2" data-testid="narrative-bullet-item">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" aria-hidden="true" />
                    <span className="flex-1 text-sm leading-relaxed text-gray-800">{item.text}</span>
                    <SourceEyeButton sourceIds={item.source_ids} />
                  </li>
                ))}
              </ul>
            );
          }

          return (
            <div key={index} className="overflow-x-auto" data-testid="narrative-table">
              <table className="w-full min-w-full border-collapse text-left text-sm">
                <thead>
                  <tr>
                    {block.headers.map((header, headerIndex) => (
                      <th key={headerIndex} className="border-b border-gray-200 px-2 py-1 font-semibold text-gray-700">
                        {header}
                      </th>
                    ))}
                    <th className="border-b border-gray-200 px-2 py-1" aria-hidden="true" />
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className="border-b border-gray-100">
                      {row.cells.map((cell, cellIndex) => (
                        <td key={cellIndex} className="px-2 py-1.5 text-gray-800">
                          {cell}
                        </td>
                      ))}
                      <td className="px-2 py-1.5 align-top">
                        <SourceEyeButton sourceIds={row.source_ids} />
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
        <div className="mt-3 rounded border border-gray-200 bg-white p-2" data-testid="category-sources">
          <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Fuentes verificables</h5>
          <ul className="mt-2 space-y-2" data-testid="category-sources-list">
            {paragraphSources.map((source) => (
              <li key={source.id}>
                <button
                  type="button"
                  className="w-full rounded border border-gray-200 px-2 py-1 text-left text-xs text-blue-500 hover:border-primary"
                  onClick={() => handleViewParagraphSource(source.id)}
                >
                  <span className="font-semibold">{source.document_name}</span>
                  <span>{` · pág. ${source.page}`}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {verifiedSources.length === 0 ? (
        <p className="mt-3 text-xs text-gray-600" data-testid="category-sources-empty">
          Sin evidencia clickeable para esta categoría. No puede marcarse como revisada automáticamente.
        </p>
      ) : null}
    </section>
  );
}
