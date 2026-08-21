import type { ConfidenceLevel } from "../features/analysis-detail/types";

export function getConfidenceLevel(score: number): ConfidenceLevel {
  if (score >= 0.8) {
    return "high";
  }
  if (score >= 0.6) {
    return "medium";
  }
  return "low";
}

const CONFIDENCE_RANK: Record<ConfidenceLevel, number> = { low: 0, medium: 1, high: 2 };

/** Confianza de un bloque que combina varios ítems: nunca optimista — usa la
 * más baja de los ítems que lo sustentan (mismo criterio que la síntesis del
 * backend, `_response_base.txt` regla 4). */
export function lowestConfidenceLevel(levels: ConfidenceLevel[]): ConfidenceLevel {
  return levels.reduce(
    (lowest, level) => (CONFIDENCE_RANK[level] < CONFIDENCE_RANK[lowest] ? level : lowest),
    "high" as ConfidenceLevel,
  );
}
