import { useMutation } from "@tanstack/react-query";

import { startAnalysis } from "../api/analyses";
import type { AnalysisStartResponse } from "../types/analysis";

export function useCheckDuplicates() {
  return useMutation<AnalysisStartResponse, Error, string>({
    mutationFn: async (analysisId: string) => startAnalysis(analysisId, { decisions: [] }),
  });
}
