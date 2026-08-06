import { Badge, type BadgeTone } from "../../components/Badge";
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

function getStatusTone(status: AnalysisDetail["status"]): BadgeTone {
  switch (status) {
    case "validated":
      return "success";
    case "analyzed":
      return "info";
    case "error":
      return "error";
    case "cancelled":
      return "neutral";
    default:
      return "warning";
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
          <Badge tone={getStatusTone(analysis.status)}>{analysis.status}</Badge>
          <Button type="button" size="sm">Validar análisis</Button>
        </div>
      </div>
    </header>
  );
}
