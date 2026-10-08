import { AlertTriangle, Check, History } from "lucide-react";

import { CATEGORY_NAMES } from "../../utils/categoryIcons";
import type { AnalysisVersion, CategoryData, CategoryId } from "./types";

interface VersionHistoryTabProps {
  versions: AnalysisVersion[];
  currentVersionId: string;
  selectedVersionId: string;
  onSelectVersion: (versionId: string) => void;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Fecha no disponible";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

const EXTRA_CATEGORY_NAMES: Record<string, string> = {
  preview_criterios: "Preview",
};

function categoryLabel(categoryId: string): string {
  return CATEGORY_NAMES[categoryId as CategoryId] ?? EXTRA_CATEGORY_NAMES[categoryId] ?? categoryId;
}

function summarizeCategoryChips(
  extractedData: Record<CategoryId, CategoryData> | undefined,
): { chips: string[]; more: number } {
  if (!extractedData) {
    return { chips: [], more: 0 };
  }
  const available = Object.entries(extractedData)
    .filter(([, category]) => (category?.items?.length ?? 0) > 0)
    .map(([categoryId]) => categoryLabel(categoryId));

  return { chips: available.slice(0, 3), more: Math.max(0, available.length - 3) };
}

export function VersionHistoryTab({
  versions,
  currentVersionId,
  selectedVersionId,
  onSelectVersion,
}: VersionHistoryTabProps) {
  const sortedVersions = [...versions].sort((a, b) => b.version_number - a.version_number);

  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-5 py-[18px]" data-testid="version-history-panel">
      <span className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[rgba(0,153,219,.12)] text-[#0099DB]">
          <History className="h-[15px] w-[15px]" />
        </span>
        <span className="font-display text-base font-semibold text-[#003C6B]">
          Historial de versiones ({sortedVersions.length})
        </span>
      </span>
      <p className="mt-1.5 text-[13px] leading-[1.5] text-[rgba(0,60,107,.68)]">
        Cada reanálisis crea una nueva versión. Podés revisar cómo quedó extraída la información en cada una.
      </p>

      <section aria-label="Historial de versiones" className="mt-2.5 flex flex-col gap-2.5">
        {sortedVersions.map((version) => {
          const isCurrent = version.id === currentVersionId;
          const isSelected = version.id === selectedVersionId;
          const conflictsCount = Object.keys(version.conflicts ?? {}).length;
          const { chips, more } = summarizeCategoryChips(version.extracted_data);

          return (
            <button
              key={version.id}
              type="button"
              onClick={() => onSelectVersion(version.id)}
              aria-pressed={isSelected}
              data-testid={`version-item-${version.version_number}`}
              className={`flex w-full items-stretch overflow-hidden rounded-2xl border bg-white text-left ${
                isSelected ? "border-[#0099DB] bg-[#F4F9FC]" : "border-[rgba(0,60,107,.12)]"
              }`}
            >
              <div
                className="w-1 flex-shrink-0"
                style={{ background: isCurrent || isSelected ? "#0099DB" : "rgba(0,60,107,.12)" }}
              />
              <div className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-3 px-[18px] py-3.5">
                <div className="flex min-w-0 flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-display text-[15px] font-semibold text-[#003C6B]">
                      Versión {version.version_number}
                    </h3>
                    {isCurrent ? (
                      <span
                        data-testid="current-version-badge"
                        className="inline-flex rounded-full bg-[rgba(127,243,222,.35)] px-2.5 py-[3px] text-[11px] font-bold text-[#0B6B58]"
                      >
                        Versión actual
                      </span>
                    ) : null}
                    {conflictsCount > 0 ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-[rgba(169,102,255,.14)] px-2.5 py-[3px] text-[11px] font-bold text-[#6E2FC9]">
                        <AlertTriangle className="h-[11px] w-[11px]" strokeWidth={2.5} />
                        {conflictsCount} conflicto{conflictsCount === 1 ? "" : "s"}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-[rgba(0,60,107,.55)]">
                    {formatDateTime(version.created_at)}
                    {version.created_by ? ` · ${version.created_by}` : ""}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {chips.map((chip) => (
                      <span
                        key={chip}
                        className="inline-flex rounded-full bg-[rgba(0,60,107,.06)] px-2.5 py-[3px] text-[11px] font-semibold text-[rgba(0,60,107,.68)]"
                      >
                        {chip}
                      </span>
                    ))}
                    {more > 0 ? (
                      <span className="inline-flex items-center text-[11px] font-semibold text-[rgba(0,60,107,.45)]">
                        +{more}
                      </span>
                    ) : null}
                  </div>
                </div>
                <span
                  className={`inline-flex h-[30px] flex-shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-xs font-semibold ${
                    isSelected ? "bg-[#003C6B] text-white" : "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]"
                  }`}
                >
                  {isSelected ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
                  {isSelected ? "Viendo esta versión" : "Ver esta versión"}
                </span>
              </div>
            </button>
          );
        })}
      </section>
    </div>
  );
}
