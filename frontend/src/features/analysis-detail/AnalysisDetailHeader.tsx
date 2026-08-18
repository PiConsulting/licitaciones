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

// FIX (2026-08-13): el H1 usaba directamente el campo "Objeto" de
// objeto_alcance como título. Ese campo está pensado para ser una síntesis
// descriptiva de 2-4 oraciones (ver backend/analysis/extraction/prompts/
// objeto_alcance.txt), no un título corto -- de hecho el diseño original ya
// preveía lo contrario (ver comentario en
// backend/analysis/extraction/synthesis.py: "identificacion_procedimiento...
// usada solo para el titulo/subtitulo del analisis"). Con la mejora de esa
// síntesis, el H1 terminaba mostrando el párrafo completo en vez de un título
// corto y diferenciado. `buildShortTitle` arma un título corto a partir de
// tipo de procedimiento + número (con dedupe: el campo "Procedimiento"
// extraído a veces ya incluye el tipo, ej. "Contratación Directa N°
// 014/2026"), con fallbacks razonables.
//
// FIX (2026-08-13, seguimiento): al principio se mostraba el objeto completo
// acá abajo, aparte del título, como descripción -- pero la categoría
// "Objeto y Alcance" ya se muestra como su propia tarjeta más abajo en la
// página (ver `CategorySection`), así que era información duplicada. El
// header ya no repite el objeto; el H1 corto + el subtítulo (organismo/
// expediente) alcanzan para identificar el análisis de un vistazo.
//
// FIX (2026-08-13, seguimiento 2): un pliego sin número de procedimiento
// asignado todavía (ver la regla correspondiente en
// backend/analysis/extraction/prompts/identificacion_procedimiento.txt)
// dejaba el título en solo "Licitación Privada" -- sin nada que diga QUÉ se
// licita. Se agregó `denominacion` (título corto de la carátula, o uno
// armado a partir del objeto si el pliego no trae uno propio) como
// reemplazo del número cuando este no existe. El backend nunca sintetiza acá
// el objeto completo -- eso sigue siendo trabajo de `objeto_alcance`.
function buildShortTitle(
  tipoProcedimiento: string | null,
  procedimiento: string | null,
  denominacion: string | null,
  organismo: string | null,
  analysisName: string | null | undefined,
  filename: string | undefined,
  analysisId: string,
): string {
  // El número de procedimiento es el identificador más preciso cuando
  // existe; si no, la denominación (título corto) cumple el mismo rol de
  // "qué sigue al tipo de procedimiento" en el título.
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

export function AnalysisDetailHeader({ analysis }: AnalysisDetailHeaderProps) {
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
  // Sin tipo/número/denominación, `buildShortTitle` cae al organismo como
  // título -- en ese caso no lo repetimos en el subtítulo (se veía el mismo
  // texto dos veces seguidas).
  const titleUsesOrganismo = !tipoProcedimiento && !procedimiento && !denominacion && Boolean(organismo);
  const subtitle = (titleUsesOrganismo ? [expediente] : [organismo, expediente]).filter(Boolean).join(" · ");
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
