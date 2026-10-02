import type { DeadlineResponse } from "../types/timeline";

/**
 * `day_type` solo es significativo cuando `unit === "días"` (ver backend
 * `HitoTemporalExtracted.tipo_dias`: "solo aplica cuando unidad es 'días'").
 * Para horas/meses/años el backend igual persiste el sentinel
 * "no_especificado" (columna NOT NULL con default, ver `timeline/models_orm.py`)
 * porque el campo no tiene sentido ahí -- mostrarlo ahí es el bug real
 * reportado ("72 horas no_especificado"). Para `unit === "días"`, en cambio,
 * "no_especificado" SÍ es información real (el pliego no aclaró hábiles vs.
 * corridos), así que se muestra como aclaración.
 */
const DAY_TYPE_LABEL: Record<string, string> = {
  corridos: "corridos",
  hábiles: "hábiles",
  no_especificado: "(tipo no especificado)",
};

/** Texto legible de la unidad + tipo de día de un plazo, ej. "72 horas" o "10 días (tipo no especificado)". */
export function formatDeadlineDuration(deadline: Pick<DeadlineResponse, "duration" | "unit" | "day_type">): string {
  const dayTypeLabel = deadline.unit === "días" ? DAY_TYPE_LABEL[deadline.day_type] : undefined;
  return dayTypeLabel
    ? `${deadline.duration} ${deadline.unit} ${dayTypeLabel}`
    : `${deadline.duration} ${deadline.unit}`;
}
