import { Button } from "../../components/Button";
import type { AnalysisDetail } from "./types";

function formatDate(dateIso: string): string {
  const date = new Date(dateIso);
  if (Number.isNaN(date.getTime())) {
    return "Fecha no disponible";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function getStatusBadgeClass(status: AnalysisDetail["status"]): string {
  switch (status) {
    case "validated":
      return "bg-success-light text-success";
    case "analyzed":
      return "bg-info-light text-info";
    case "error":
      return "bg-error-light text-error";
    case "cancelled":
      return "bg-gray-100 text-gray-600";
    default:
      return "bg-warning-light text-warning";
  }
}

interface AnalysisHeaderProps {
  analysis: AnalysisDetail;
}

export function AnalysisHeader({ analysis }: AnalysisHeaderProps) {
  const primaryDocument = analysis.documents.find((doc) => doc.is_primary) ?? analysis.documents[0];
  const displayName = primaryDocument?.filename ?? `Análisis ${analysis.id}`;

  return (
    <header className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">{displayName}</h1>
          <p className="mt-1 text-sm text-gray-600">Organismo: No disponible</p>
          <p className="text-sm text-gray-600">Fecha: {formatDate(analysis.created_at)}</p>
        </div>

        <div className="flex items-center gap-2">
          <span className={`rounded px-2 py-1 text-xs font-semibold uppercase ${getStatusBadgeClass(analysis.status)}`}>
            {analysis.status}
          </span>
          <Button type="button" size="sm">Validar análisis</Button>
        </div>
      </div>
    </header>
  );
}
