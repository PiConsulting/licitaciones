import type { AnalysisStatusResponse } from "../../types/analysis";
import { CATEGORY_LABELS } from "./ReanalyzeModal";
import { CancelButton } from "./CancelButton";
import { ProgressBar } from "./ProgressBar";
import { TimeoutWarning } from "./TimeoutWarning";

const REANALYSIS_TYPE_LABELS: Record<string, string> = {
  all: "Todo",
  phase1: "Fase 1",
  phase2: "Fase 2",
  categories: "Categorías seleccionadas",
};

function formatCategoriesSummary(categories: string[] | undefined): string {
  if (!categories || categories.length === 0) {
    return "";
  }
  const labels = categories.map((id) => CATEGORY_LABELS[id] ?? id);
  if (labels.length <= 3) {
    return labels.join(", ");
  }
  return `${labels.slice(0, 3).join(", ")} +${labels.length - 3}`;
}

function formatStartedAt(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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
  const categoriesSummary = formatCategoriesSummary(status.reanalysis_categories);
  const startedAt = formatStartedAt(status.reanalysis_started_at);

  return (
    <div className="flex flex-col gap-4">
      <ProgressBar
        stage={status.current_stage}
        progress={status.progress_percentage}
        isProcessing={isProcessing || isQueued}
        stageProgress={status.stage_progress}
        metaSlot={
          hasReanalysisMetadata ? (
            <div className="flex flex-wrap items-center gap-2" data-testid="reanalyze-progress-meta">
              <span className="inline-flex rounded-full bg-[rgba(169,102,255,.14)] px-3 py-[5px] text-xs font-bold text-[#6E2FC9]">
                Reanálisis · {REANALYSIS_TYPE_LABELS[status.reanalysis_type ?? ""] ?? "Reanálisis"}
              </span>
              {categoriesSummary ? (
                <span className="text-xs text-[rgba(0,60,107,.55)]">{categoriesSummary}</span>
              ) : null}
              {startedAt ? (
                <>
                  <span className="h-3 w-px bg-[rgba(0,60,107,.15)]" />
                  <span className="text-xs text-[rgba(0,60,107,.55)]">Inicio: {startedAt}</span>
                </>
              ) : null}
            </div>
          ) : null
        }
      />

      {isProcessing || isQueued ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-[rgba(0,60,107,.55)]">
            {hasReanalysisMetadata
              ? "Podés seguir navegando el análisis: el reanálisis sigue en segundo plano y vas a ver la nueva versión cuando termine."
              : "Podés cerrar esta pantalla: el análisis sigue en segundo plano."}
          </span>
          {isProcessing ? (
            <CancelButton analysisId={analysisId} label={hasReanalysisMetadata ? "Cancelar reanálisis" : "Cancelar análisis"} />
          ) : null}
        </div>
      ) : null}

      <TimeoutWarning show={shouldShowTimeoutWarning} />

      {status.status === "error" ? (
        <div className="rounded-2xl border border-[rgba(220,38,38,.3)] bg-[#FEF2F2] px-4 py-3 text-[13px] text-[#B91C1C]">
          {status.error_message || "Error en el análisis"}
        </div>
      ) : null}

      {status.status === "cancelled" ? (
        <div className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-[#F4F9FC] px-4 py-3 text-sm text-[rgba(0,60,107,.68)]">
          El análisis fue cancelado
        </div>
      ) : null}
    </div>
  );
}
