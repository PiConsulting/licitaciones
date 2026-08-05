import { useParams } from "react-router-dom";

import { AnalysisDetailPage } from "../features/analysis-detail/AnalysisDetailPage";

export default function AnalysisDetail() {
  const { analysisId } = useParams();

  if (!analysisId) {
    return <p className="text-sm text-error">ID de análisis inválido.</p>;
  }

  return <AnalysisDetailPage analysisId={analysisId} />;
}
