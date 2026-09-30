import type { MouseEvent } from "react";
import { Play, RotateCcw, Trash2 } from "lucide-react";

import { getBusinessUnitColor } from "../../../config/businessUnits";
import type { AnalysisListItem, AnalysisListSortBy, AnalysisListSortOrder } from "../../../types/analysis";
import { isRunningAnalysisStatus } from "../../../utils/analysisStatus";
import { ProgressBar } from "./ProgressBar";

interface AnalysisTableProps {
  items: AnalysisListItem[];
  sortBy: AnalysisListSortBy;
  sortOrder: AnalysisListSortOrder;
  onSort: (column: AnalysisListSortBy) => void;
  onRowClick: (analysisId: string) => void;
  onStartAnalysis?: (analysisId: string) => void;
  onRetryAnalysis?: (analysisId: string) => void;
  onDeleteAnalysis?: (item: AnalysisListItem) => void;
  retryingAnalysisId?: string | null;
  deletingAnalysisId?: string | null;
}

function formatDate(value: string): string {
  const localDateMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const date = localDateMatch
    ? new Date(Number(localDateMatch[1]), Number(localDateMatch[2]) - 1, Number(localDateMatch[3]))
    : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatEstimatedAmount(amount?: number | null, currency?: string | null): string {
  if (amount == null || Number.isNaN(amount)) {
    return "—";
  }

  // `maximumFractionDigits: 0` redondeaba los centavos hasta perderlos del todo
  // (ej. USD 654.484,26 se mostraba como "$654.484", sin el ",26"). 0-2
  // decimales: se muestran solo si el monto realmente los tiene.
  const normalizedCurrency = (currency ?? "ARS").toUpperCase();
  if (normalizedCurrency === "ARS") {
    return `$ ${new Intl.NumberFormat("es-AR", { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(amount)}`;
  }

  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: normalizedCurrency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}

// Bug real (2026-09-29): este mapa se quedó con los 5 valores provisorios de
// la story FE5.1 original ("aprobada" incluido) y nunca se actualizó cuando
// el enum real de `BusinessStatus` (backend/analysis/models.py) pasó a 7
// valores sin "aprobada" -- cualquier análisis en en_analisis/pendiente_decision/
// no_aprobada caía siempre en el fallback "Sin informar" aunque tuviera un
// estado real y válido en la base.
function toBusinessStatusLabel(value?: string | null): string {
  if (!value) {
    return "Sin informar";
  }

  const normalized = value.trim().toLowerCase();
  const labels: Record<string, string> = {
    en_analisis: "En análisis",
    pendiente_decision: "Pendiente de decisión",
    no_aprobada: "No aprobada",
    en_revision: "En revisión",
    presentada: "Presentada",
    ganada: "Ganada",
    perdida: "Perdida",
  };

  return labels[normalized] ?? "Sin informar";
}

function getBusinessStatusClasses(value?: string | null): string {
  const normalized = value?.trim().toLowerCase();
  const styles: Record<string, string> = {
    en_analisis: "bg-cedi-navy-8 text-cedi-navy-68",
    pendiente_decision: "bg-[#FEF3C7] text-[#92400E]",
    no_aprobada: "bg-[#FEE2E2] text-[#B91C1C]",
    en_revision: "bg-[#F3E8FF] text-[#6E2FC9]",
    presentada: "bg-[#E0E7FF] text-[#2F4EF8]",
    ganada: "bg-[#CCFBF1] text-[#0B6B58]",
    perdida: "bg-cedi-navy-8 text-cedi-navy-68",
  };
  return styles[normalized ?? ""] ?? "bg-cedi-navy-8 text-cedi-navy-68";
}

function sortIndicator(active: boolean, sortOrder: AnalysisListSortOrder): string {
  if (!active) {
    return "";
  }
  return sortOrder === "asc" ? " ▲" : " ▼";
}

function canDeleteStatus(status: string): boolean {
  return !isRunningAnalysisStatus(status);
}

const STAGE_LABELS: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Preparando para análisis",
  analyzing: "Analizando",
  consolidating: "Consolidando",
  completed: "Completado",
};

function translateStage(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

export function AnalysisTable({
  items,
  sortBy,
  sortOrder,
  onSort,
  onRowClick,
  onStartAnalysis,
  onRetryAnalysis,
  onDeleteAnalysis,
  retryingAnalysisId,
  deletingAnalysisId,
}: AnalysisTableProps) {
  const onRowSelect = (event: MouseEvent<HTMLTableRowElement>, analysisId: string) => {
    const element = event.target as HTMLElement;
    if (element.closest("[data-menu='true']")) {
      return;
    }
    onRowClick(analysisId);
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-cedi-navy-12 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-[#F4F9FC]">
            <tr className="border-b border-cedi-navy-12">
              <th className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">PLIEGO</th>
              <th className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">UNIDAD</th>
              <th className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">ESTADO</th>
              <th className="whitespace-nowrap px-4 py-3 text-right text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">MONTO ESTIMADO</th>
              <th className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">APERTURA / CIERRE</th>
              <th className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">ETAPA</th>
              <th className="whitespace-nowrap px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">
                <button type="button" className="hover:text-cedi-navy" onClick={() => onSort("created_at")}>
                  FECHA{sortIndicator(sortBy === "created_at", sortOrder)}
                </button>
              </th>
              <th className="whitespace-nowrap px-4 py-3 text-right text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68">ACCIONES</th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {items.map((item) => (
              <tr
                key={item.id}
                onClick={(event) => onRowSelect(event, item.id)}
                className="cursor-pointer border-b border-cedi-navy-8 hover:bg-[#F4F9FC]"
              >
                <td className="min-w-[260px] px-4 py-3.5">
                  <p className="text-sm font-semibold leading-[1.35] text-cedi-navy">{item.analysis_name ?? item.primary_document_name ?? `Análisis ${item.id.slice(0, 8)}`}</p>
                  <p className="mt-1 text-xs text-cedi-navy-68">{item.organismo ?? "Sin informar"}</p>
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 text-sm font-semibold text-cedi-navy">
                  {item.business_unit ? (
                    <span className="inline-flex items-center gap-[7px] text-[13px] font-semibold">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: getBusinessUnitColor(item.business_unit) }} aria-hidden="true" />
                      {item.business_unit}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 text-sm text-cedi-navy">
                  <span
                    className={[
                      "inline-flex rounded-full px-3 py-[5px] text-xs font-semibold",
                      getBusinessStatusClasses(item.business_status),
                    ].join(" ")}
                  >
                    {toBusinessStatusLabel(item.business_status)}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 text-right font-display text-sm font-semibold text-cedi-navy">
                  {formatEstimatedAmount(item.monto_estimado, item.moneda)}
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 text-[13px] text-cedi-navy">
                  <span>{formatDate(item.opening_date ?? "")}</span>
                  <span className="px-1 text-cedi-navy-30">→</span>
                  <span>{formatDate(item.closing_date ?? "")}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 text-sm text-cedi-navy-68">
                  {isRunningAnalysisStatus(item.status) ? (
                    <ProgressBar
                      stage={item.current_stage}
                      progress={item.progress_percentage}
                      stageProgress={item.stage_progress}
                    />
                  ) : (
                    <span>{translateStage(item.current_stage)}</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 text-sm text-cedi-navy-68">{formatDate(item.created_at)}</td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center justify-end gap-1.5">
                    {item.status.toLowerCase() === "draft" ? (
                      <button
                        type="button"
                        data-menu="true"
                        aria-label={retryingAnalysisId === item.id ? "Iniciando análisis" : "Iniciar análisis"}
                        title={retryingAnalysisId === item.id ? "Iniciando análisis" : "Iniciar análisis"}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border-[1.5px] border-cedi-navy-20 bg-white text-cedi-celeste hover:border-cedi-celeste hover:bg-[#F4F9FC] disabled:cursor-not-allowed disabled:opacity-40"
                        onClick={() => onStartAnalysis?.(item.id)}
                        disabled={!onStartAnalysis || retryingAnalysisId === item.id}
                      >
                        <Play size={16} aria-hidden="true" className={retryingAnalysisId === item.id ? "animate-pulse" : undefined} />
                      </button>
                    ) : null}

                    {item.status.toLowerCase() === "error" ? (
                      <button
                        type="button"
                        data-menu="true"
                        aria-label={retryingAnalysisId === item.id ? "Reintentando análisis" : "Reintentar análisis"}
                        title={retryingAnalysisId === item.id ? "Reintentando análisis" : "Reintentar análisis"}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border-[1.5px] border-cedi-navy-20 bg-white text-cedi-navy hover:border-cedi-celeste hover:bg-[#F4F9FC] disabled:cursor-not-allowed disabled:opacity-40"
                        onClick={() => onRetryAnalysis?.(item.id)}
                        disabled={!onRetryAnalysis || retryingAnalysisId === item.id}
                      >
                        <RotateCcw size={16} aria-hidden="true" className={retryingAnalysisId === item.id ? "animate-spin" : undefined} />
                      </button>
                    ) : null}

                    {canDeleteStatus(item.status) ? (
                      <button
                        type="button"
                        data-menu="true"
                        aria-label="Eliminar análisis"
                        title="Eliminar análisis"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border-[1.5px] border-cedi-navy-20 bg-white text-cedi-navy-55 hover:border-error hover:bg-red-50 hover:text-error disabled:cursor-not-allowed disabled:opacity-40"
                        onClick={() => onDeleteAnalysis?.(item)}
                        disabled={!onDeleteAnalysis || deletingAnalysisId === item.id}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
