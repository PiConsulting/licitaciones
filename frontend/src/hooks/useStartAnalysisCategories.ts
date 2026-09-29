import { useMutation } from "@tanstack/react-query";

import { decideAnalysisCategories } from "../api/analyses";
import type { CategoriesDecision, CategoriesDecisionResponse } from "../types/analysis";

interface CategoriesDecisionVariables {
  analysisId: string;
  decision: CategoriesDecision;
}

export function useCategoriesDecision() {
  return useMutation<CategoriesDecisionResponse, Error, CategoriesDecisionVariables>({
    mutationFn: async ({ analysisId, decision }) => decideAnalysisCategories(analysisId, decision),
  });
}
