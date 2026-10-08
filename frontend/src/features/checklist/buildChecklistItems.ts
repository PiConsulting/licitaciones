import type { CategoryData, CategoryId, CategoryNarrative } from "../analysis-detail/types";
import { buildNarrativeBlocks } from "../analysis-detail/utils/narrativeSynthesis";
import { splitLabelAndValue } from "../analysis-detail/utils/splitLabelAndValue";
import type { TrackingItem } from "../../types/tracking";

export interface ChecklistItemContent {
  trackingItem: TrackingItem;
  label: string;
  text: string;
  page: number | null;
}

interface ContentEntry {
  text: string;
  titulo?: string;
  page: number | null;
  /** (documento, página) de TODAS las fuentes del bullet/fila, no solo la
   * primera -- un bullet consolidado por la síntesis (ver `resolveContent`)
   * puede citar más de una página, y el tracking item "sobrante" que hay que
   * recuperar puede corresponder a cualquiera de ellas. */
  sourceLocations: Array<{ documentId: string; page: number }>;
}

export function buildChecklistItemContents(
  category: CategoryData,
  categoryId: CategoryId,
  trackingItems: TrackingItem[],
): ChecklistItemContent[] {
  const narrative: CategoryNarrative = category.narrative ?? buildNarrativeBlocks(category, categoryId);
  const sourceById = new Map(narrative.sources.map((source) => [source.id, source]));

  const resolveSources = (sourceIds: number[]) =>
    sourceIds
      .map((id) => sourceById.get(id))
      .filter((source): source is (typeof narrative.sources)[number] => Boolean(source));

  const buildEntry = (text: string, sourceIds: number[], titulo?: string): ContentEntry => {
    const sources = resolveSources(sourceIds);
    return {
      text,
      titulo,
      page: sources[0]?.page ?? null,
      sourceLocations: sources.map((source) => ({ documentId: source.document_id, page: source.page })),
    };
  };

  const contents: ContentEntry[] = [];
  for (const block of narrative.blocks) {
    if (block.type === "bullet_list") {
      for (const item of block.items) {
        contents.push(buildEntry(item.text, item.source_ids, item.titulo));
      }
    } else if (block.type === "table") {
      for (const row of block.rows) {
        contents.push(buildEntry(row.cells.join(" · "), row.source_ids));
      }
    } else if (block.type === "paragraph" && trackingItems.length === 1 && contents.length === 0) {
      contents.push(buildEntry(block.text, block.source_ids));
    }
  }

  /** La síntesis puede consolidar varios items crudos en menos bullets (dato
   * real, no un bug -- ej. dos alternativas del mismo requisito quedan en un
   * solo bullet). Cuando eso corre la posición del tracking item fuera de
   * `contents`, buscar por (documento, página) evita mostrar el `tipo` crudo
   * sin desarrollar (bug real reportado: un ítem aparecía como "Documento" a
   * secas). El emparejamiento por posición sigue siendo el camino normal --
   * esto es solo la red de contención para cuando no alcanza. */
  function resolveContent(trackingItem: TrackingItem, index: number): ContentEntry | undefined {
    const direct = contents[index];
    if (direct) {
      return direct;
    }
    const ref = trackingItem.source_item_ref;
    if (ref.document_id && ref.page != null) {
      return contents.find((content) =>
        content.sourceLocations.some((location) => location.documentId === ref.document_id && location.page === ref.page),
      );
    }
    return undefined;
  }

  return trackingItems.map((trackingItem, index) => {
    const content = resolveContent(trackingItem, index);
    if (!content) {
      return {
        trackingItem,
        label: trackingItem.source_item_ref.field_name,
        text: "",
        page: trackingItem.source_item_ref.page ?? null,
      };
    }
    const titulo = content.titulo?.trim();
    const split = titulo ? null : splitLabelAndValue(content.text);
    return {
      trackingItem,
      label: titulo || split?.label || trackingItem.source_item_ref.field_name,
      text: titulo ? content.text : (split?.value ?? content.text),
      page: content.page ?? trackingItem.source_item_ref.page ?? null,
    };
  });
}
