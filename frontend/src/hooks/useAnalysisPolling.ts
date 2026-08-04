import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { getAnalysisStatus } from "../api/analyses";

export function useAnalysisPolling(analysisId: string, enabled: boolean) {
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["analysis-status", analysisId],
    queryFn: () => getAnalysisStatus(analysisId),
    enabled: enabled && analysisId.length > 0,
    refetchInterval: (queryContext) => {
      const status = queryContext.state.data?.status;
      if (status === "completed" || status === "error") {
        return false;
      }
      return 3000;
    },
    staleTime: 0,
  });

  useEffect(() => {
    if (query.data?.status === "completed") {
      navigate(`/analysis/${analysisId}`);
    }
  }, [analysisId, navigate, query.data?.status]);

  return query;
}
