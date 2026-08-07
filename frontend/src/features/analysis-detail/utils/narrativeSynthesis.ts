import { CATEGORY_NAMES, CHECKLIST_CATEGORIES, SINGLE_PARAGRAPH_CATEGORIES } from "../../../utils/categoryIcons";
import { getConfidenceLevel, lowestConfidenceLevel } from "../../../utils/confidence";
import type {
  CategoryData,
  CategoryId,
  CategoryNarrative,
  FieldItem,
  NarrativeBulletItem,
  NarrativeParagraphBlock,
  NarrativeSource,
} from "../types";
import { dedupeNarrativeSources } from "./dedupeCitations";
import { joinAsEnumeratedClause } from "./naturalLanguage";

/** Frase de apertura para el párrafo único de las categorías en
 * `SINGLE_PARAGRAPH_CATEGORIES` — sin esto, el párrafo arranca directo con el
 * primer hecho enumerado, sin contexto de qué está respondiendo. */
const SINGLE_PARAGRAPH_LEAD_IN: Partial<Record<CategoryId, string>> = {
  requisitos_admisibilidad: "El pliego exige los siguientes requisitos de admisibilidad",
  causales_rechazo: "El pliego establece que serán causales de rechazo de la oferta",
};

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
 * Arma el único párrafo de una categoría en `SINGLE_PARAGRAPH_CATEGORIES`:
 * une el valor de cada ítem extraído en una sola cláusula enumerada, en vez de
 * una viñeta por ítem — esas categorías tienen que verse como una sola
 * respuesta, nunca como una tarjeta por requisito/causal.
 */
function buildSingleParagraphBlock(
  items: FieldItem[],
  categoryId: CategoryId,
  sourceIndex: Map<string, number>,
  sources: NarrativeSource[],
): NarrativeParagraphBlock | null {
  const extracted = items.filter(
    (item) => item.field_state === "extraido" && normalizeText(item.field_value) !== "",
  );
  if (extracted.length === 0) {
    return null;
  }

  const leadIn = SINGLE_PARAGRAPH_LEAD_IN[categoryId];
  const clause = joinAsEnumeratedClause(extracted.map((item) => normalizeText(item.field_value)));
  const text = leadIn ? `${leadIn}: ${clause}` : clause;

  const sourceIds = [...new Set(extracted.flatMap((item) => collectSourceIds(item, sourceIndex, sources)))];
  const confidenceLevel = lowestConfidenceLevel(extracted.map((item) => getConfidenceLevel(item.confidence)));

  return { type: "paragraph", text, confidence_level: confidenceLevel, source_ids: sourceIds };
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

  if (SINGLE_PARAGRAPH_CATEGORIES.has(categoryId)) {
    const block = buildSingleParagraphBlock(items, categoryId, sourceIndex, sources);
    if (!block) {
      return { blocks: [fallbackBlock(categoryId)], sources: [] };
    }
    return { blocks: [block], sources: dedupeNarrativeSources(sources) };
  }

  const useBulletList = CHECKLIST_CATEGORIES.has(categoryId) || items.length > 1;

  if (!useBulletList) {
    const [singleItem] = items;
    const text = fieldSentence(singleItem) ?? fallbackBlock(categoryId).text;
    return {
      blocks: [
        {
          type: "paragraph",
          text,
          confidence_level: getConfidenceLevel(singleItem.confidence),
          source_ids: collectSourceIds(singleItem, sourceIndex, sources),
        },
      ],
      sources: dedupeNarrativeSources(sources),
    };
  }

  const bulletItems = items
    .map((item): NarrativeBulletItem | null => {
      const text = fieldSentence(item);
      if (!text) {
        return null;
      }
      return {
        text,
        confidence_level: getConfidenceLevel(item.confidence),
        source_ids: collectSourceIds(item, sourceIndex, sources),
      };
    })
    .filter((entry): entry is NarrativeBulletItem => entry !== null);

  if (bulletItems.length === 0) {
    return { blocks: [fallbackBlock(categoryId)], sources: [] };
  }

  return {
    blocks: [{ type: "bullet_list", items: bulletItems }],
    sources: dedupeNarrativeSources(sources),
  };
}
