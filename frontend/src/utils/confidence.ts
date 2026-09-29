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
