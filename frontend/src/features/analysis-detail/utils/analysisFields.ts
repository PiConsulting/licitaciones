import type { AnalysisDetail, CategoryId } from "../types";

const NOT_FOUND_VALUE = "No encontrado";

/** Busca el valor de un campo puntual dentro de una categoría ya extraída. */
export function getFieldValue(
  analysis: AnalysisDetail,
  categoryId: CategoryId,
  fieldName: string,
): string | null {
  const category = analysis.current_version?.extracted_data?.[categoryId];
  if (!category || !Array.isArray(category.items)) {
    return null;
  }

  const item = category.items.find((field) => field.field_name === fieldName);
  if (!item?.field_value || item.field_value === NOT_FOUND_VALUE) {
    return null;
  }

  return item.field_value;
}
