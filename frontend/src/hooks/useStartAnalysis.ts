import { useMutation } from "@tanstack/react-query";

import { startAnalysis } from "../api/analyses";
import type { AnalysisStartPayload, AnalysisStartResponse } from "../types/analysis";

interface StartAnalysisVariables {
  analysisId: string;
  payload?: AnalysisStartPayload;
}

export function useStartAnalysis() {
  return useMutation<AnalysisStartResponse, Error, StartAnalysisVariables>({
    mutationFn: async ({ analysisId, payload }) => startAnalysis(analysisId, payload),
  });
}
