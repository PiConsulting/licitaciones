import { CATEGORY_NAMES } from "../../../utils/categoryIcons";
import type { CategoryData, CategoryId, FieldItem } from "../types";

function describeField(field: FieldItem): string {
  switch (field.field_state) {
    case "extraido":
      return `${field.field_name}: ${field.field_value ?? "sin valor registrado"}.`;
    case "no_encontrado":
      return `No se encontró información sobre ${field.field_name.toLowerCase()}.`;
    case "no_aplica":
      return `${field.field_name} no aplica para este pliego.`;
    case "en_conflicto":
      return `${field.field_name} presenta valores en conflicto entre los documentos analizados.`;
    default:
      return "";
  }
}

/**
 * Arma un párrafo en lenguaje natural a partir de los campos ya extraídos de
 * una categoría. Es un reemplazo temporal, solo de frontend, del texto que en
 * el futuro va a generar un LLM a partir de la misma metadata — por eso
 * `CategorySection` prioriza `category.narrative` (el campo que el backend
 * va a empezar a completar) y solo cae acá si todavía no existe.
 */
export function buildCategoryNarrative(category: CategoryData, categoryId: CategoryId): string {
  if (category.items.length === 0) {
    return `No se encontró información sobre ${CATEGORY_NAMES[categoryId].toLowerCase()} en el pliego.`;
  }

  return category.items.map(describeField).filter(Boolean).join(" ");
}
