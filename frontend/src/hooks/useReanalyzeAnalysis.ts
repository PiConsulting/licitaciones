import { useMutation } from "@tanstack/react-query";

import { reanalyzeAnalysis } from "../api/analyses";
import type { ReanalyzeRequest, ReanalyzeResponse } from "../types/analysis";

interface ReanalyzeVariables {
  analysisId: string;
  payload: ReanalyzeRequest;
}

export function useReanalyzeAnalysis() {
  return useMutation<ReanalyzeResponse, Error, ReanalyzeVariables>({
    mutationFn: async ({ analysisId, payload }) => reanalyzeAnalysis(analysisId, payload),
  });
}
