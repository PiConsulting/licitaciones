import { CATEGORY_NAMES } from "../../../utils/categoryIcons";
import type { CategoryData, CategoryId, Citation, FieldItem } from "../types";

const BULLET_ITEM_THRESHOLD = 4;
const BULLET_TEXT_THRESHOLD = 280;
const DEFAULT_CATEGORY_SUMMARY = "Sin datos extraídos todavía.";

export interface NarrativeSynthesis {
  text: string;
  intro: string | null;
  bullets: string[];
  representativeCitation: Citation | null;
  hasUsefulData: boolean;
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim();
}

function toNaturalSentence(field: FieldItem): string {
  const fieldLabel = field.field_name.trim();
  switch (field.field_state) {
    case "extraido": {
      const value = normalizeText(field.field_value);
      if (!value) {
        return `${fieldLabel}: sin valor registrado.`;
      }
      return `${fieldLabel}: ${value}.`;
    }
    case "no_encontrado":
      return `No se encontró información sobre ${fieldLabel.toLowerCase()}.`;
    case "no_aplica":
      return `${fieldLabel} no aplica para este pliego.`;
    case "en_conflicto":
      return `${fieldLabel} presenta valores en conflicto entre documentos.`;
    default:
      return "";
  }
}

function toBulletItem(field: FieldItem): string {
  const fieldLabel = field.field_name.trim();
  switch (field.field_state) {
    case "extraido": {
      const value = normalizeText(field.field_value);
      return value ? `${fieldLabel}: ${value}` : `${fieldLabel}: sin valor registrado`;
    }
    case "no_encontrado":
      return `${fieldLabel}: no encontrado`;
    case "no_aplica":
      return `${fieldLabel}: no aplica`;
    case "en_conflicto":
      return `${fieldLabel}: conflicto entre documentos`;
    default:
      return fieldLabel;
  }
}

function getRepresentativeCitation(items: FieldItem[]): Citation | null {
  const extractedCitation = items
    .filter((item) => item.field_state === "extraido")
    .flatMap((item) => item.citations)
    .find((citation) => normalizeText(citation.text) !== "");

  if (extractedCitation) {
    return extractedCitation;
  }

  return items
    .flatMap((item) => item.citations)
    .find((citation) => normalizeText(citation.text) !== "") ?? null;
}

function resolveFallback(categoryId: CategoryId): string {
  return `No se encontró información útil para ${CATEGORY_NAMES[categoryId].toLowerCase()}.`;
}

export function buildNarrativeSynthesis(category: CategoryData, categoryId: CategoryId): NarrativeSynthesis {
  const summary = normalizeText(category.summary);
  const items = category.items;

  if (items.length === 0) {
    return {
      text: resolveFallback(categoryId),
      intro: null,
      bullets: [],
      representativeCitation: null,
      hasUsefulData: false,
    };
  }

  const sentences = items.map(toNaturalSentence).filter(Boolean);
  const text = sentences.join(" ");
  const extractedItems = items.filter((item) => item.field_state === "extraido");
  const hasUsefulData = extractedItems.some((item) => normalizeText(item.field_value) !== "");
  const useBullets =
    items.length >= BULLET_ITEM_THRESHOLD || text.length >= BULLET_TEXT_THRESHOLD;

  if (!hasUsefulData) {
    return {
      text: resolveFallback(categoryId),
      intro: null,
      bullets: [],
      representativeCitation: getRepresentativeCitation(items),
      hasUsefulData: false,
    };
  }

  if (!useBullets) {
    return {
      text,
      intro: null,
      bullets: [],
      representativeCitation: getRepresentativeCitation(items),
      hasUsefulData: true,
    };
  }

  const bullets = items.map(toBulletItem);
  const intro =
    summary && summary !== DEFAULT_CATEGORY_SUMMARY
      ? summary
      : `Se identificaron ${items.length} elementos relevantes en ${CATEGORY_NAMES[categoryId].toLowerCase()}.`;

  return {
    text,
    intro,
    bullets,
    representativeCitation: getRepresentativeCitation(items),
    hasUsefulData: true,
  };
}
