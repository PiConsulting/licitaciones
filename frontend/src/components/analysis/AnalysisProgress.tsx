import type { AnalysisStatusResponse } from "../../types/analysis";
import { CancelButton } from "./CancelButton";
import { ProgressBar } from "./ProgressBar";
import { TimeoutWarning } from "./TimeoutWarning";

function getReanalysisLabel(type: AnalysisStatusResponse["reanalysis_type"]): string {
  switch (type) {
    case "all":
      return "Reanálisis completo";
    case "phase1":
      return "Reanálisis fase 1";
    case "phase2":
      return "Reanálisis fase 2";
    case "categories":
      return "Reanálisis por categorías";
    default:
      return "Reanálisis";
  }
}

interface AnalysisProgressProps {
  analysisId: string;
  status: AnalysisStatusResponse;
}

export function AnalysisProgress({ analysisId, status }: AnalysisProgressProps) {
  const isProcessing = status.status === "processing";
  const isQueued = status.status === "queued";
  const shouldShowTimeoutWarning =
    isProcessing &&
    !!status.timeout_warning_at &&
    new Date().getTime() >= new Date(status.timeout_warning_at).getTime();
  const hasReanalysisMetadata = Boolean(status.reanalysis_type);

  return (
    <div className="space-y-3">
      <ProgressBar
        stage={status.current_stage}
        progress={status.progress_percentage}
        isProcessing={isProcessing || isQueued}
        stageProgress={status.stage_progress}
      />

      {hasReanalysisMetadata ? (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900" data-testid="reanalyze-progress-meta">
          <p className="font-semibold">{getReanalysisLabel(status.reanalysis_type)}</p>
          {status.reanalysis_categories && status.reanalysis_categories.length > 0 ? (
            <p className="mt-1">{`Categorías: ${status.reanalysis_categories.join(", ")}`}</p>
          ) : null}
          {status.reanalysis_started_at ? (
            <p className="mt-1">{`Inicio: ${new Date(status.reanalysis_started_at).toLocaleString("es-AR")}`}</p>
          ) : null}
        </div>
      ) : null}

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
