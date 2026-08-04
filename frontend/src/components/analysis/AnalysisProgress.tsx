import type { AnalysisStatusResponse } from "../../types/analysis";
import { CancelButton } from "./CancelButton";
import { ProgressBar } from "./ProgressBar";
import { TimeoutWarning } from "./TimeoutWarning";

interface AnalysisProgressProps {
  analysisId: string;
  status: AnalysisStatusResponse;
}

export function AnalysisProgress({ analysisId, status }: AnalysisProgressProps) {
  const isProcessing = status.status === "processing";
  const shouldShowTimeoutWarning =
    isProcessing &&
    !!status.timeout_warning_at &&
    new Date().getTime() >= new Date(status.timeout_warning_at).getTime();

  return (
    <div className="space-y-3">
      <ProgressBar
        stage={status.current_stage}
        progress={status.progress_percentage}
        isProcessing={isProcessing}
        stageProgress={status.stage_progress}
      />

      <TimeoutWarning show={shouldShowTimeoutWarning} />

      {isProcessing ? <CancelButton analysisId={analysisId} /> : null}

      {status.status === "error" ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {status.error_message || "Error en el analisis"}
        </div>
      ) : null}

      {status.status === "cancelled" ? (
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
          El analisis fue cancelado
        </div>
      ) : null}
    </div>
  );
}
