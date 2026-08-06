import { getConfidenceLevel } from "./confidence";
import type { FieldItem } from "../features/analysis-detail/types";

/** True when a field needs the user's attention (full card + action buttons)
 * rather than a compact, informational row. */
export function needsAction(field: FieldItem): boolean {
  if (field.field_state === "en_conflicto" || field.field_state === "no_encontrado") {
    return true;
  }
  if (field.field_state === "extraido") {
    return getConfidenceLevel(field.confidence) !== "high";
  }
  return false;
}

const STATE_RANK: Record<FieldItem["field_state"], number> = {
  en_conflicto: 0,
  no_encontrado: 1,
  no_aplica: 2,
  extraido: 3,
};

export function sortFieldsBySeverity(items: FieldItem[]): FieldItem[] {
  return [...items].sort((a, b) => {
    const stateDelta = STATE_RANK[a.field_state] - STATE_RANK[b.field_state];
    if (stateDelta !== 0) {
      return stateDelta;
    }

    if (a.field_state === "extraido" && b.field_state === "extraido") {
      return a.confidence - b.confidence;
    }

    return a.field_name.localeCompare(b.field_name);
  });
}
