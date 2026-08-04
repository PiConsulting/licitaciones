import { useQuery } from "@tanstack/react-query";

import { getAnalysisStatus } from "../api/analyses";

const POLLING_INTERVAL_MS = 3000;

export function useAnalysisStatus(analysisId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["analysis", analysisId, "status"],
    queryFn: () => getAnalysisStatus(analysisId),
    enabled: enabled && analysisId.length > 0,
    refetchInterval: (queryContext) => {
      const status = queryContext.state.data?.status;
      if (status === "analyzed" || status === "error" || status === "cancelled") {
        return false;
      }
      return POLLING_INTERVAL_MS;
    },
    refetchIntervalInBackground: true,
    staleTime: 0,
  });
}
