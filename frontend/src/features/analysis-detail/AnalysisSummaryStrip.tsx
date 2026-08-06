import { Badge } from "../../components/Badge";
import { CATEGORY_ICONS, CATEGORY_NAMES } from "../../utils/categoryIcons";
import type { AnalysisDetail, CategoryId } from "./types";
import { getAnalysisSummary } from "./utils/categoryStats";

interface AnalysisSummaryStripProps {
  analysis: AnalysisDetail;
}

export function AnalysisSummaryStrip({ analysis }: AnalysisSummaryStripProps) {
  const summary = getAnalysisSummary(analysis);

  const handleChipClick = (categoryId: CategoryId) => {
    document.getElementById(`category-${categoryId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section aria-label="Resumen de extracción" className="mb-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm font-semibold text-gray-900">
          {`${summary.extractedCategories}/${summary.totalCategories} categorías extraídas`}
        </p>
        {summary.conflict > 0 ? <Badge tone="error">{`${summary.conflict} conflictos`}</Badge> : null}
        {summary.notFound > 0 ? <Badge tone="warning">{`${summary.notFound} no encontrados`}</Badge> : null}
      </div>

      {summary.categoriesNeedingReview.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-600">Necesitan revisión:</span>
          {summary.categoriesNeedingReview.map((categoryId) => {
            const Icon = CATEGORY_ICONS[categoryId];
            return (
              <button
                key={categoryId}
                type="button"
                onClick={() => handleChipClick(categoryId)}
                className="inline-flex items-center gap-1.5 rounded-full border border-highlight/30 bg-highlight-light px-3 py-1 text-xs font-medium text-highlight hover:bg-highlight/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
              >
                <Icon className="h-3.5 w-3.5" />
                {CATEGORY_NAMES[categoryId]}
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
