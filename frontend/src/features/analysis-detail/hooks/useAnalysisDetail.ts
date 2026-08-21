import { useQuery } from "@tanstack/react-query";

import { getAnalysisById } from "../../../services/api/analysisApi";

export function useAnalysisDetail(analysisId: string) {
  return useQuery({
    queryKey: ["analysis", analysisId, "detail"],
    queryFn: () => getAnalysisById(analysisId),
    enabled: analysisId.length > 0,
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: true,
    refetchInterval: false,
  });
}
