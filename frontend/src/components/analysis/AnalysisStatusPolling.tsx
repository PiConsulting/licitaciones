import type { AnalysisStatusResponse } from "../../types/analysis";

interface AnalysisStatusPollingProps {
  statusData: AnalysisStatusResponse | undefined;
  isLoading: boolean;
  error: string | null;
}

const STATUS_LABELS: Record<AnalysisStatusResponse["status"], string> = {
  draft: "Borrador",
  queued: "En cola",
  processing: "Procesando",
  analyzed: "Análisis finalizado",
  error: "Error",
  cancelled: "Cancelado",
};

const STAGE_LABELS: Record<AnalysisStatusResponse["current_stage"], string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Preparando para análisis",
  analyzing: "Analizando categorias",
  consolidating: "Consolidando",
  completed: "Analizado",
};

export function AnalysisStatusPolling({ statusData, isLoading, error }: AnalysisStatusPollingProps) {
  if (isLoading) {
    return <p className="text-sm text-gray-600">Consultando estado del análisis...</p>;
  }

  if (error) {
    return <p className="text-sm text-error">{error}</p>;
  }

  if (!statusData) {
    return null;
  }

  const extractedData = statusData.extracted_data as Record<string, unknown> | undefined;
  const hasFailedCategory =
    statusData.status === "analyzed" &&
    !!extractedData &&
    Object.entries(extractedData).some(
      ([key, value]) => key.endsWith("_extraction_status") && value === "failed",
    );

  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
      <p>
        Estado actual: <strong>{STATUS_LABELS[statusData.status]}</strong>
      </p>
      <p>Etapa: {statusData.stage_progress || STAGE_LABELS[statusData.current_stage]}</p>
      {hasFailedCategory ? (
        <>
          <p className="mt-2 font-semibold text-amber-700">Análisis completo con advertencias</p>
          <p className="text-amber-700">Algunas categorías no pudieron extraerse</p>
        </>
      ) : null}
    </div>
  );
}
