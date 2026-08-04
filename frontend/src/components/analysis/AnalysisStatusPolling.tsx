import type { AnalysisStatusResponse } from "../../types/analysis";

interface AnalysisStatusPollingProps {
  statusData: AnalysisStatusResponse | undefined;
  isLoading: boolean;
  error: string | null;
}

const STATUS_LABELS: Record<AnalysisStatusResponse["status"], string> = {
  draft: "Borrador",
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Indexando documentos",
  analyzing: "Analizando contenido",
  analyzed: "Análisis finalizado",
  completed: "Completado",
  error: "Error",
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

  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
      <p>
        Estado actual: <strong>{STATUS_LABELS[statusData.status]}</strong>
      </p>
      {statusData.current_stage ? <p>Etapa: {statusData.current_stage}</p> : null}
    </div>
  );
}
