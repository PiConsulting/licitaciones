import { Check, Circle, CircleSlash, X } from "lucide-react";

import type { TrackingItem, TrackingItemStatus } from "../../../types/tracking";
import type { CategoryNarrative, Citation, NarrativeBlockData, NarrativeSource } from "../types";
import { SourceEyeButton as EyeButton } from "./SourceEyeButton";

interface NarrativeBlocksProps {
  narrative: CategoryNarrative;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
  trackingItems?: TrackingItem[];
  isTrackingClosed?: boolean;
  loadingTrackingItemId?: string | null;
  onChangeTrackingItemStatus?: (trackingItemId: string, status: TrackingItemStatus) => void;
}

const TRACKING_ITEM_STATUS_OPTIONS: Array<{
  value: TrackingItemStatus;
  label: string;
  icon: typeof Circle;
  selectedClassName: string;
  idleClassName: string;
}> = [
  {
    value: "not_evaluated",
    label: "Sin evaluar",
    icon: Circle,
    selectedClassName: "border-gray-500 bg-gray-500 text-white",
    idleClassName: "border-gray-200 bg-white text-gray-600 hover:border-gray-500 hover:text-gray-700",
  },
  {
    value: "compliant",
    label: "Cumple",
    icon: Check,
    selectedClassName: "border-success bg-success text-white",
    idleClassName: "border-gray-200 bg-white text-success hover:border-success hover:bg-success-light",
  },
  {
    value: "non_compliant",
    label: "No cumple",
    icon: X,
    selectedClassName: "border-error bg-error text-white",
    idleClassName: "border-gray-200 bg-white text-error hover:border-error hover:bg-error-light",
  },
  {
    value: "not_applicable",
    label: "No aplica",
    icon: CircleSlash,
    selectedClassName: "border-info bg-info text-white",
    idleClassName: "border-gray-200 bg-white text-info hover:border-info hover:bg-info-light",
  },
];

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
function collectParagraphSourceIds(blocks: NarrativeBlockData[]): Set<number> {
  const ids = new Set<number>();
  for (const block of blocks) {
    if (block.type === "paragraph") {
      block.source_ids.forEach((id) => ids.add(id));
    }
  }
  return ids;
}

/** Todos los `source_ids` que efectivamente usa algún bloque/bullet/fila.
 * Una fuente que ningún elemento referencia no puede aparecer en ningún lado:
 * mostrarla sugiere una trazabilidad que no existe. */
function collectReferencedSourceIds(blocks: NarrativeBlockData[]): Set<number> {
  const ids = new Set<number>();
  for (const block of blocks) {
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

interface TrackingItemControlsProps {
  item: TrackingItem;
  isClosed: boolean;
  isLoading: boolean;
  onChangeStatus?: (trackingItemId: string, status: TrackingItemStatus) => void;
}

function TrackingItemControls({ item, isClosed, isLoading, onChangeStatus }: TrackingItemControlsProps) {
  if (isClosed) {
    const selected = TRACKING_ITEM_STATUS_OPTIONS.find((option) => option.value === item.status);
    if (!selected) {
      return null;
    }
    const Icon = selected.icon;
    return (
      <div className="flex shrink-0 items-center gap-1" data-testid={`inline-tracking-item-${item.tracking_item_id}`}>
        <span
          className={`inline-flex h-7 w-7 items-center justify-center rounded border text-xs ${selected.selectedClassName}`}
          aria-label={`${selected.label}: ${item.source_item_ref.field_name}`}
          title={selected.label}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
      </div>
    );
  }

  return (
    <div className="flex shrink-0 items-center gap-1" data-testid={`inline-tracking-item-${item.tracking_item_id}`}>
      {TRACKING_ITEM_STATUS_OPTIONS.map((option) => {
        const Icon = option.icon;
        const isSelected = item.status === option.value;
        return (
          <button
            key={option.value}
            type="button"
            className={`inline-flex h-7 w-7 items-center justify-center rounded border text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
              isSelected ? option.selectedClassName : option.idleClassName
            }`}
            disabled={isClosed || isLoading || !onChangeStatus}
            onClick={() => onChangeStatus?.(item.tracking_item_id, option.value)}
            aria-label={`${option.label}: ${item.source_item_ref.field_name}`}
            title={option.label}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
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
  trackingItems = [],
  isTrackingClosed = false,
  loadingTrackingItemId = null,
  onChangeTrackingItemStatus,
}: NarrativeBlocksProps) {
  const referencedSourceIds = collectReferencedSourceIds(narrative.blocks);
  const paragraphSourceIds = collectParagraphSourceIds(narrative.blocks);

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

  function InlineTrackingControls({ itemIndex }: { itemIndex: number }) {
    const item = trackingItems[itemIndex];
    if (!item) {
      return null;
    }
    return (
      <TrackingItemControls
        item={item}
        isClosed={isTrackingClosed}
        isLoading={loadingTrackingItemId === item.tracking_item_id}
        onChangeStatus={onChangeTrackingItemStatus}
      />
    );
  }

  let trackingItemIndex = 0;

  return (
    <section className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3" data-testid="narrative-blocks">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Respuesta</h4>

      <div className="mt-2 space-y-3">
        {narrative.blocks.map((block, index) => {
          if (block.type === "paragraph") {
            return (
              <div key={index} className="flex items-start gap-2" data-testid="narrative-paragraph">
                <p className="flex-1 text-sm leading-relaxed text-gray-800">{block.text}</p>
                {trackingItems.length === 1 ? <InlineTrackingControls itemIndex={0} /> : null}
              </div>
            );
          }

          if (block.type === "bullet_list") {
            return (
              <div key={index} data-testid="narrative-bullet-list">
                <ul className="space-y-1.5">
                  {block.items.map((item, itemIndex) => {
                    const currentTrackingItemIndex = trackingItemIndex;
                    trackingItemIndex += 1;

                    return (
                      <li key={itemIndex} className="flex items-start gap-2" data-testid="narrative-bullet-item">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" aria-hidden="true" />
                        <span className="flex-1 text-sm leading-relaxed text-gray-800">{item.text}</span>
                        <InlineTrackingControls itemIndex={currentTrackingItemIndex} />
                        <SourceEyeButton sourceIds={item.source_ids} />
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
                      <th key={headerIndex} className="border-b border-gray-200 px-2 py-1 font-semibold text-gray-700">
                        {header}
                      </th>
                    ))}
                    <th className="border-b border-gray-200 px-2 py-1" aria-hidden="true" />
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, rowIndex) => {
                    const currentTrackingItemIndex = trackingItemIndex;
                    trackingItemIndex += 1;
                    return (
                    <tr key={rowIndex} className="border-b border-gray-100">
                      {row.cells.map((cell, cellIndex) => (
                        <td key={cellIndex} className="px-2 py-1.5 text-gray-800">
                          {cell}
                        </td>
                      ))}
                      <td className="px-2 py-1.5 align-top">
                        <div className="flex items-center justify-end gap-2">
                          <InlineTrackingControls itemIndex={currentTrackingItemIndex} />
                        <SourceEyeButton sourceIds={row.source_ids} />
                        </div>
                      </td>
                    </tr>
                    );
                  })}
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
