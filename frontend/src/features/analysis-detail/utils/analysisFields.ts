import type { AnalysisDetail, CategoryId, FieldItem } from "../types";

const NOT_FOUND_VALUE = "No encontrado";

/** Busca el ítem completo (valor + citas) de un campo puntual dentro de una
 * categoría ya extraída. `getFieldValue` es un atajo sobre esto que descarta
 * las citas -- usar esta función cuando además se necesite la fuente (ej. el
 * ícono de "ver fuente" del presupuesto oficial). */
export function getFieldItem(
  analysis: AnalysisDetail,
  categoryId: CategoryId,
  fieldName: string,
): FieldItem | null {
  const category = analysis.current_version?.extracted_data?.[categoryId];
  if (!category || !Array.isArray(category.items)) {
    return null;
  }

  const item = category.items.find((field) => field.field_name === fieldName);
  if (!item?.field_value || item.field_value === NOT_FOUND_VALUE) {
    return null;
  }

  return item;
}

/** Busca el valor de un campo puntual dentro de una categoría ya extraída. */
export function getFieldValue(
  analysis: AnalysisDetail,
  categoryId: CategoryId,
  fieldName: string,
): string | null {
  return getFieldItem(analysis, categoryId, fieldName)?.field_value ?? null;
}

/** Título corto para identificar un análisis (header de detalle Y breadcrumb
 * del layout -- antes cada uno tenía su propia lógica, y el breadcrumb no
 * usaba tipo/número/denominación de `datos_procedimiento`, así que para
 * cualquier análisis sin `analysis_name` cargado a mano mostraba "Análisis
 * <id>" mientras el título de arriba ya mostraba algo con sentido). */
export function buildAnalysisShortTitle(analysis: AnalysisDetail): string {
  const tipoProcedimiento = getFieldValue(analysis, "datos_procedimiento", "Tipo de procedimiento");
  const procedimiento = getFieldValue(analysis, "datos_procedimiento", "Procedimiento");
  const denominacion = getFieldValue(analysis, "datos_procedimiento", "Denominación");
  const organismo = getFieldValue(analysis, "datos_procedimiento", "Organismo convocante");
  const primaryDocument = analysis.documents.find((document) => document.is_primary) ?? analysis.documents[0];

  const numeroODenominacion = procedimiento ?? denominacion;
  if (tipoProcedimiento && numeroODenominacion) {
    if (numeroODenominacion.toLowerCase().startsWith(tipoProcedimiento.toLowerCase())) {
      return numeroODenominacion;
    }
    return `${tipoProcedimiento} — ${numeroODenominacion}`;
  }
  return (
    tipoProcedimiento ??
    numeroODenominacion ??
    organismo ??
    analysis.analysis_name ??
    primaryDocument?.filename ??
    `Análisis ${analysis.id}`
  );
}
