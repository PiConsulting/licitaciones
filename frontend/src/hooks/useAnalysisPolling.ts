import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import { useAnalysisStatus } from "./useAnalysisStatus";

interface UseAnalysisPollingOptions {
  onCompleted?: () => void;
}

export function useAnalysisPolling(analysisId: string, enabled: boolean, options: UseAnalysisPollingOptions = {}) {
  const navigate = useNavigate();
  const query = useAnalysisStatus(analysisId, enabled);
  const hasCompletedRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      hasCompletedRef.current = false;
    }
  }, [enabled]);

  useEffect(() => {
    if (query.data?.status === "analyzed" && !hasCompletedRef.current) {
      hasCompletedRef.current = true;
      options.onCompleted?.();
      navigate(`/analysis/${analysisId}`);
    }
  }, [analysisId, navigate, options, query.data?.status]);

  return query;
}
