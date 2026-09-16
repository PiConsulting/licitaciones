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

function summarizeCategories(extractedData: Record<CategoryId, CategoryData> | undefined): string {
  if (!extractedData) {
    return "Sin categorías";
  }
  const available = Object.entries(extractedData)
    .filter(([, category]) => (category?.items?.length ?? 0) > 0)
    .map(([categoryId]) => CATEGORY_NAMES[categoryId as CategoryId] ?? categoryId);

  if (available.length === 0) {
    return "Sin categorías con contenido";
  }
  if (available.length <= 3) {
    return available.join(", ");
  }
  return `${available.slice(0, 3).join(", ")} +${available.length - 3}`;
}

export function VersionHistoryTab({
  versions,
  currentVersionId,
  selectedVersionId,
  onSelectVersion,
}: VersionHistoryTabProps) {
  const sortedVersions = [...versions].sort((a, b) => b.version_number - a.version_number);

  return (
    <section aria-label="Historial de versiones" className="space-y-3">
      {sortedVersions.map((version) => {
        const isCurrent = version.id === currentVersionId;
        const isSelected = version.id === selectedVersionId;

        return (
          <button
            key={version.id}
            type="button"
            className={`w-full rounded-lg border p-4 text-left transition ${
              isSelected ? "border-primary bg-blue-50/40" : "border-slate-200 hover:border-slate-300"
            }`}
            onClick={() => onSelectVersion(version.id)}
            data-testid={`version-item-${version.version_number}`}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-gray-900">Versión {version.version_number}</p>
              {isCurrent ? (
                <span className="rounded-full bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-700" data-testid="current-version-badge">
                  Versión actual
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-gray-600">{formatDateTime(version.created_at)}</p>
            <p className="mt-2 text-xs text-gray-700">{summarizeCategories(version.extracted_data)}</p>
          </button>
        );
      })}
    </section>
  );
}
