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

function getOrganismo(analysis: AnalysisDetail): string {
  try {
    const datosProcedimiento = analysis.current_version?.extracted_data?.datos_procedimiento;
    if (!datosProcedimiento || !Array.isArray(datosProcedimiento.items)) {
      return "Organismo no disponible";
    }

    const organismoItem = datosProcedimiento.items.find(
      (item: any) => item.field_name === "Organismo convocante"
    );

    if (organismoItem?.field_value && organismoItem.field_value !== "No encontrado") {
      return organismoItem.field_value;
    }

    return "Organismo no disponible";
  } catch {
    return "Organismo no disponible";
  }
}

interface AnalysisDetailHeaderProps {
  analysis: AnalysisDetail;
}

export function AnalysisDetailHeader({ analysis }: AnalysisDetailHeaderProps) {
  const primaryDocument = analysis.documents.find((doc) => doc.is_primary) ?? analysis.documents[0];
  const displayName = primaryDocument?.filename ?? `Análisis ${analysis.id}`;
  const totalPages = analysis.documents.reduce((sum, doc) => sum + (doc.page_count || 0), 0);
  const organismo = getOrganismo(analysis);

  return (
    <header className="mb-4 rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
      {/* Línea principal: Título + Organismo (inline) */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold text-gray-900">
            {displayName}
            <span className="ml-2 text-sm font-normal text-gray-600">
              {organismo}
            </span>
          </h1>
        </div>

        {/* Botones de acción alineados a la derecha */}
        <div className="flex items-center gap-2">
          <Button type="button" size="sm">Validar análisis</Button>
        </div>
      </div>

      {/* Línea secundaria: Badge de estado + Fecha + Páginas totales */}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <Badge tone={getStatusTone(analysis.status)}>{analysis.status}</Badge>
        <span className="inline-flex items-center">
          <span className="mr-1">•</span>
          {formatDate(analysis.created_at)}
        </span>
        <span className="inline-flex items-center">
          <span className="mr-1">•</span>
          {totalPages} {totalPages === 1 ? "página" : "páginas"}
        </span>
      </div>
    </header>
  );
}
