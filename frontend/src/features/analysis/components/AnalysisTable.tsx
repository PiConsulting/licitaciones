import type { MouseEvent } from "react";

import type { AnalysisListItem, AnalysisListSortBy, AnalysisListSortOrder } from "../../../types/analysis";
import { ProgressBar } from "./ProgressBar";
import { StatusBadge } from "./StatusBadge";

interface AnalysisTableProps {
  items: AnalysisListItem[];
  sortBy: AnalysisListSortBy;
  sortOrder: AnalysisListSortOrder;
  onSort: (column: AnalysisListSortBy) => void;
  onRowClick: (analysisId: string) => void;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function sortIndicator(active: boolean, sortOrder: AnalysisListSortOrder): string {
  if (!active) {
    return "";
  }
  return sortOrder === "asc" ? " ▲" : " ▼";
}

function isRunningStatus(status: string): boolean {
  return status === "queued" || status === "analyzing";
}

const STAGE_LABELS: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Indexando",
  analyzing: "Analizando",
  consolidating: "Consolidando",
  completed: "Completado",
};

function translateStage(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

export function AnalysisTable({ items, sortBy, sortOrder, onSort, onRowClick }: AnalysisTableProps) {
  const onRowSelect = (event: MouseEvent<HTMLTableRowElement>, analysisId: string) => {
    const element = event.target as HTMLElement;
    if (element.closest("[data-menu='true']")) {
      return;
    }
    onRowClick(analysisId);
  };

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">PLIEGO</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">ORGANISMO</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                <button type="button" className="hover:text-primary" onClick={() => onSort("status")}>
                  ESTADO{sortIndicator(sortBy === "status", sortOrder)}
                </button>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                <button type="button" className="hover:text-primary" onClick={() => onSort("current_stage")}>
                  ETAPA{sortIndicator(sortBy === "current_stage", sortOrder)}
                </button>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                <button type="button" className="hover:text-primary" onClick={() => onSort("created_at")}>
                  FECHA{sortIndicator(sortBy === "created_at", sortOrder)}
                </button>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">CREADO POR</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">ACCIONES</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {items.map((item) => (
              <tr
                key={item.id}
                onClick={(event) => onRowSelect(event, item.id)}
                className="cursor-pointer hover:bg-primary-light/30"
              >
                <td className="px-4 py-3 text-sm text-gray-900">{item.primary_document_name ?? `Análisis ${item.id.slice(0, 8)}`}</td>
                <td className="px-4 py-3 text-sm text-gray-700">{item.organismo ?? "No disponible"}</td>
                <td className="px-4 py-3 text-sm text-gray-700">
                  <StatusBadge status={item.status} />
                </td>
                <td className="px-4 py-3 text-sm text-gray-700">
                  {isRunningStatus(item.status) ? (
                    <ProgressBar
                      stage={item.current_stage}
                      progress={item.progress_percentage}
                      stageProgress={item.stage_progress}
                    />
                  ) : (
                    <span>{translateStage(item.current_stage)}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-700">{formatDate(item.created_at)}</td>
                <td className="px-4 py-3 text-sm text-gray-700">{item.created_by_name ?? "Desconocido"}</td>
                <td className="px-4 py-3 text-sm text-gray-700">
                  <button
                    type="button"
                    data-menu="true"
                    className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                  >
                    Menú
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
