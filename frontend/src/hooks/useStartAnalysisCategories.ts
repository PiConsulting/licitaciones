import { useMutation } from "@tanstack/react-query";

import { startAnalysisCategories } from "../api/analyses";
import type { AnalysisStartResponse } from "../types/analysis";

interface StartAnalysisCategoriesVariables {
  analysisId: string;
}

export function useStartAnalysisCategories() {
  return useMutation<AnalysisStartResponse, Error, StartAnalysisCategoriesVariables>({
    mutationFn: async ({ analysisId }) => startAnalysisCategories(analysisId),
  });
}
