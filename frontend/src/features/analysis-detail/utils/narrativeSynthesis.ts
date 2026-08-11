import { CATEGORY_NAMES, CHECKLIST_CATEGORIES } from "../../../utils/categoryIcons";
import { getConfidenceLevel } from "../../../utils/confidence";
import type {
  CategoryData,
  CategoryId,
  CategoryNarrative,
  FieldItem,
  NarrativeBulletItem,
  NarrativeParagraphBlock,
  NarrativeSource,
} from "../types";
import { dedupeNarrativeSources, remapSourceIds } from "./dedupeCitations";

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim();
}

/** Una oración natural por ítem — nunca `campo: valor` crudo, ya que
 * `field_name`/`field_value` ya vienen humanizados desde `analysisApi.ts`. */
function fieldSentence(field: FieldItem): string | null {
  const fieldLabel = field.field_name.trim();
  switch (field.field_state) {
    case "extraido": {
      const value = normalizeText(field.field_value);
      return value ? `${fieldLabel}: ${value}.` : null;
    }
    case "no_encontrado":
      return `No se encontró información sobre ${fieldLabel.toLowerCase()}.`;
    case "no_aplica":
      return `${fieldLabel} no aplica para este pliego.`;
    case "en_conflicto":
      return `${fieldLabel} presenta valores en conflicto entre documentos.`;
    default:
      return null;
  }
}

/** Junta las citas clickeables de un ítem en la lista de fuentes deduplicada,
 * devolviendo los `source_ids` que le corresponden a ese ítem. */
function collectSourceIds(
  field: FieldItem,
  sourceIndex: Map<string, number>,
  sources: NarrativeSource[],
): number[] {
  const ids: number[] = [];
  for (const citation of field.citations) {
    if (!citation.document_id.trim() || citation.page <= 0 || !citation.text.trim()) {
      continue;
    }
    const key = `${citation.document_id}|${citation.page}|${citation.text.trim().toLowerCase()}`;
    let id = sourceIndex.get(key);
    if (id === undefined) {
      id = sources.length;
      sourceIndex.set(key, id);
      sources.push({
        id,
        document_id: citation.document_id,
        document_name: citation.document_name,
        page: citation.page,
        text: citation.text,
      });
    }
    ids.push(id);
  }
  return ids;
}

function fallbackBlock(categoryId: CategoryId): NarrativeParagraphBlock {
  return {
    type: "paragraph",
    text: `No se encontró información sobre ${CATEGORY_NAMES[categoryId].toLowerCase()} en el pliego.`,
    confidence_level: "low",
    source_ids: [],
  };
}

/**
 * Fallback de frontend para cuando el backend todavía no emitió `narrative`
 * para una categoría (la síntesis por LLM no corrió o falló). Produce la
 * misma forma de bloques que la síntesis del backend, para que el renderer
 * (`NarrativeBlocks`) no necesite dos caminos distintos. A diferencia del
 * backend, este fallback nunca arma un bloque `table` — esa decisión queda
 * reservada al LLM, que es quien puede juzgar con criterio si el contenido de
 * ese pliego puntual amerita una tabla.
 */
export function buildNarrativeBlocks(category: CategoryData, categoryId: CategoryId): CategoryNarrative {
  const items = category.items;

  if (items.length === 0) {
    return { blocks: [fallbackBlock(categoryId)], sources: [] };
  }

  const hasUsefulData = items.some(
    (item) => item.field_state === "extraido" && normalizeText(item.field_value) !== "",
  );
  if (!hasUsefulData) {
    return { blocks: [fallbackBlock(categoryId)], sources: [] };
  }

  const sources: NarrativeSource[] = [];
  const sourceIndex = new Map<string, number>();

  // El formato no es fijo por categoría: varios hechos discretos e
  // independientes van en lista, una idea única va en párrafo. Nunca se
  // fuerza a juntar todo en un solo párrafo solo porque la categoría "suele"
  // tener pocos datos -- eso llevaba a respuestas ilegibles cuando el pliego
  // real tenía muchos hechos para esa categoría.
  const useBulletList = CHECKLIST_CATEGORIES.has(categoryId) || items.length > 1;

  if (!useBulletList) {
    const [singleItem] = items;
    const text = fieldSentence(singleItem) ?? fallbackBlock(categoryId).text;
    const sourceIds = collectSourceIds(singleItem, sourceIndex, sources);
    const { sources: dedupedSources, idMapping } = dedupeNarrativeSources(sources);
    return {
      blocks: [
        {
          type: "paragraph",
          text,
          confidence_level: getConfidenceLevel(singleItem.confidence),
          source_ids: remapSourceIds(sourceIds, idMapping),
        },
      ],
      sources: dedupedSources,
    };
  }

  const bulletDrafts = items
    .map((item): { text: string; confidence_level: NarrativeBulletItem["confidence_level"]; sourceIds: number[] } | null => {
      const text = fieldSentence(item);
      if (!text) {
        return null;
      }
      return {
        text,
        confidence_level: getConfidenceLevel(item.confidence),
        sourceIds: collectSourceIds(item, sourceIndex, sources),
      };
    })
    .filter((entry): entry is { text: string; confidence_level: NarrativeBulletItem["confidence_level"]; sourceIds: number[] } => entry !== null);

  if (bulletDrafts.length === 0) {
    return { blocks: [fallbackBlock(categoryId)], sources: [] };
  }

  const { sources: dedupedSources, idMapping } = dedupeNarrativeSources(sources);
  const bulletItems: NarrativeBulletItem[] = bulletDrafts.map((draft) => ({
    text: draft.text,
    confidence_level: draft.confidence_level,
    source_ids: remapSourceIds(draft.sourceIds, idMapping),
  }));

  return {
    blocks: [{ type: "bullet_list", items: bulletItems }],
    sources: dedupedSources,
  };
}
