import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import { Badge, type BadgeTone } from "../../components/Badge";
import { Button } from "../../components/Button";
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
    case "en_revision":
      return "warning";
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
    case "en_revision":
      return "En revisión";
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
  rightActions?: ReactNode;
  showStartTrackingAction?: boolean;
  startTrackingLabel?: string;
  startTrackingLoading?: boolean;
  onStartTracking?: () => void;
}

function buildShortTitle(
  tipoProcedimiento: string | null,
  procedimiento: string | null,
  denominacion: string | null,
  organismo: string | null,
  analysisName: string | null | undefined,
  filename: string | undefined,
  analysisId: string,
): string {
 
  const numeroODenominacion = procedimiento ?? denominacion;
  if (tipoProcedimiento && numeroODenominacion) {
    if (numeroODenominacion.toLowerCase().startsWith(tipoProcedimiento.toLowerCase())) {
      return numeroODenominacion;
    }
    return `${tipoProcedimiento} — ${numeroODenominacion}`;
  }
  return (
    tipoProcedimiento ??
    numeroODenominacion ??
    organismo ??
    analysisName ??
    filename ??
    `Análisis ${analysisId}`
  );
}

export function AnalysisDetailHeader({
  analysis,
  rightActions,
  showStartTrackingAction = false,
  startTrackingLabel = "Iniciar seguimiento",
  startTrackingLoading = false,
  onStartTracking,
}: AnalysisDetailHeaderProps) {
  const primaryDocument = analysis.documents.find((doc) => doc.is_primary) ?? analysis.documents[0];
  const totalPages = analysis.documents.reduce((sum, doc) => sum + (doc.page_count || 0), 0);

  const organismo = getFieldValue(analysis, "datos_procedimiento", "Organismo convocante");
  const expediente = getFieldValue(analysis, "datos_procedimiento", "Expediente");
  const procedimiento = getFieldValue(analysis, "datos_procedimiento", "Procedimiento");
  const tipoProcedimiento = getFieldValue(analysis, "datos_procedimiento", "Tipo de procedimiento");
  const denominacion = getFieldValue(analysis, "datos_procedimiento", "Denominación");
  const presupuestoOficial = getFieldValue(analysis, "datos_procedimiento", "Presupuesto oficial");

  const title = buildShortTitle(
    tipoProcedimiento,
    procedimiento,
    denominacion,
    organismo,
    analysis.analysis_name,
    primaryDocument?.filename,
    analysis.id,
  );
  // Sin tipo/número/denominación, `buildShortTitle` cae al organismo -- no lo repetimos en el subtítulo.
  const titleUsesOrganismo = !tipoProcedimiento && !procedimiento && !denominacion && Boolean(organismo);
  const subtitle = (titleUsesOrganismo ? [expediente] : [organismo, expediente]).filter(Boolean).join(" · ");
  const breadcrumbLabel = analysis.analysis_name ?? primaryDocument?.filename ?? expediente ?? analysis.id;

  return (
    <header className="relative mb-6">
      <nav className="mb-2 flex items-center text-xs text-gray-500" aria-label="Ruta de navegación">
        <span>Análisis IA</span>
        <ChevronRight className="mx-1 h-3.5 w-3.5" aria-hidden="true" />
        <span className="font-medium text-gray-900">{breadcrumbLabel}</span>
      </nav>

      <div className="min-w-0">
        <h1 className="text-xl font-bold text-gray-900">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-gray-600">{subtitle}</p> : null}
        {presupuestoOficial ? <p className="mt-1 text-sm text-gray-600">{`Presupuesto oficial: ${presupuestoOficial}`}</p> : null}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <Badge tone={getStatusTone(analysis.status)}>{getStatusLabel(analysis.status)}</Badge>
        <span>{formatDate(analysis.created_at)}</span>
        <span aria-hidden="true">·</span>
        <span>{`${totalPages} ${totalPages === 1 ? "página" : "páginas"}`}</span>
      </div>

      {rightActions ? (
        <div className="absolute right-4 bottom-0 w-full max-w-sm">
          {rightActions}
        </div>
      ) : null}

      {showStartTrackingAction && !rightActions ? (
        <div className="absolute right-4 bottom-0">
          <Button
            type="button"
            size="sm"
            onClick={onStartTracking}
            loading={startTrackingLoading}
            disabled={!onStartTracking}
          >
            {startTrackingLabel}
          </Button>
        </div>
      ) : null}
    </header>
  );
}
