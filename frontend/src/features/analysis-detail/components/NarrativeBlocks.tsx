import { FieldBadge } from "../FieldBadge";
import type { CategoryNarrative, Citation, NarrativeSource } from "../types";

interface NarrativeBlocksProps {
  narrative: CategoryNarrative;
  onViewSource?: (payload: { citation: Citation; citations: Citation[] }) => void;
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
 * Renderiza la respuesta de experto de una categoría: siempre bloques en
 * lenguaje natural (párrafo/lista/tabla), nunca `field_name: field_value`
 * crudo — ni acá ni en ningún otro lugar de esta vista. Reemplaza el antiguo
 * "Detalle por campo" y "Acciones recomendadas".
 */
export function NarrativeBlocks({ narrative, onViewSource }: NarrativeBlocksProps) {
  const allCitations = narrative.sources.map(sourceToCitation);

  const handleViewSource = (sourceIds: number[]) => {
    if (!onViewSource || sourceIds.length === 0) {
      return;
    }
    const citations = sourceIds
      .map((id) => narrative.sources.find((source) => source.id === id))
      .filter((source): source is NarrativeSource => source !== undefined)
      .map(sourceToCitation);
    if (citations.length === 0) {
      return;
    }
    onViewSource({ citation: citations[0], citations: allCitations });
  };

  return (
    <section className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3" data-testid="narrative-blocks">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Respuesta</h4>

      <div className="mt-2 space-y-3">
        {narrative.blocks.map((block, index) => {
          if (block.type === "paragraph") {
            return (
              <div key={index} className="flex items-start gap-2" data-testid="narrative-paragraph">
                <p className="flex-1 text-sm leading-relaxed text-gray-800">{block.text}</p>
                <div className="flex shrink-0 items-center gap-1">
                  <FieldBadge level={block.confidence_level} />
                </div>
              </div>
            );
          }

          if (block.type === "bullet_list") {
            return (
              <ul key={index} className="space-y-2" data-testid="narrative-bullet-list">
                {block.items.map((item, itemIndex) => (
                  <li
                    key={itemIndex}
                    className="flex items-start gap-2 rounded border border-gray-200 bg-white p-2"
                    data-testid="narrative-bullet-item"
                  >
                    <span className="flex-1 text-sm leading-relaxed text-gray-800">{item.text}</span>
                    <div className="flex shrink-0 items-center gap-1">
                      <FieldBadge level={item.confidence_level} />
                    </div>
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
                    <th className="border-b border-gray-200 px-2 py-1" />
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
                      <td className="px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          <FieldBadge level={row.confidence_level} />
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

      <div className="mt-3 rounded border border-gray-200 bg-white p-2" data-testid="category-sources">
        <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Fuentes verificables</h5>
        {narrative.sources.length > 0 ? (
          <ul className="mt-2 space-y-2" data-testid="category-sources-list">
            {narrative.sources.map((source) => (
              <li key={source.id}>
                <button
                  type="button"
                  className="w-full rounded border border-gray-200 px-2 py-1 text-left text-xs text-primary hover:border-primary"
                  onClick={() => handleViewSource([source.id])}
                >
                  <span className="font-semibold">{source.document_name}</span>
                  <span>{` · pág. ${source.page}`}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-gray-600" data-testid="category-sources-empty">
            Sin evidencia clickeable para esta categoría. No puede marcarse como revisada automáticamente.
          </p>
        )}
      </div>
    </section>
  );
}
