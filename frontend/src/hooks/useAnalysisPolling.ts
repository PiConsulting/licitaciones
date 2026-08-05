import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAnalysisStatus } from "./useAnalysisStatus";

export function useAnalysisPolling(analysisId: string, enabled: boolean) {
  const navigate = useNavigate();
  const query = useAnalysisStatus(analysisId, enabled);

  useEffect(() => {
    if (query.data?.status === "analyzed") {
      navigate(`/analysis/${analysisId}`);
    }
  }, [analysisId, navigate, query.data?.status]);

  return query;
}
