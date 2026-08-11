import { ChevronRight } from "lucide-react";

import { Badge, type BadgeTone } from "../../components/Badge";
import type { AnalysisDetail } from "./types";
import { getFieldValue } from "./utils/analysisFields";

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

function getStatusLabel(status: AnalysisDetail["status"]): string {
  switch (status) {
    case "draft":
      return "Borrador";
    case "validated":
      return "Validado";
    case "analyzed":
      return "Analizado";
    case "processing":
      return "Procesando";
    case "error":
      return "Error";
    case "cancelled":
      return "Cancelado";
    default:
      return status;
  }
}

interface AnalysisDetailHeaderProps {
  analysis: AnalysisDetail;
}

export function AnalysisDetailHeader({ analysis }: AnalysisDetailHeaderProps) {
  const primaryDocument = analysis.documents.find((doc) => doc.is_primary) ?? analysis.documents[0];
  const totalPages = analysis.documents.reduce((sum, doc) => sum + (doc.page_count || 0), 0);

  const organismo = getFieldValue(analysis, "datos_procedimiento", "Organismo convocante");
  const expediente = getFieldValue(analysis, "datos_procedimiento", "Expediente");
  const procedimiento = getFieldValue(analysis, "datos_procedimiento", "Procedimiento");
  const tipoProcedimiento = getFieldValue(analysis, "datos_procedimiento", "Tipo de procedimiento");
  const presupuestoOficial = getFieldValue(analysis, "datos_procedimiento", "Presupuesto oficial");
  const objeto = getFieldValue(analysis, "objeto_alcance", "Objeto");

  const title = objeto ?? primaryDocument?.filename ?? `Análisis ${analysis.id}`;
  const subtitle = [organismo, expediente].filter(Boolean).join(" · ");
  const procedureLine = [tipoProcedimiento, procedimiento].filter(Boolean).join(" · ");
  const breadcrumbLabel = analysis.analysis_name ?? primaryDocument?.filename ?? expediente ?? analysis.id;

  return (
    <header className="mb-6">
      <nav className="mb-2 flex items-center text-xs text-gray-500" aria-label="Ruta de navegación">
        <span>Análisis IA</span>
        <ChevronRight className="mx-1 h-3.5 w-3.5" aria-hidden="true" />
        <span className="font-medium text-gray-900">{breadcrumbLabel}</span>
      </nav>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-gray-900">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-gray-600">{subtitle}</p> : null}
          {procedureLine ? <p className="mt-1 text-sm text-gray-600">{procedureLine}</p> : null}
          {presupuestoOficial ? <p className="mt-1 text-sm text-gray-600">{`Presupuesto oficial: ${presupuestoOficial}`}</p> : null}
        </div>

        {/*
        <Button type="button" size="sm">
          Validar análisis
        </Button>
        */}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <Badge tone={getStatusTone(analysis.status)}>{getStatusLabel(analysis.status)}</Badge>
        <span>{formatDate(analysis.created_at)}</span>
        <span aria-hidden="true">·</span>
        <span>{`${totalPages} ${totalPages === 1 ? "página" : "páginas"}`}</span>
      </div>
    </header>
  );
}
