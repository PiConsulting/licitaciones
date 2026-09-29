import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CategorySection } from "./CategorySection";
import type { AnalysisDetail, CategoryData, CategoryId, Citation, NarrativeSource } from "./types";
import { getAnalysisSummary } from "./utils/categoryStats";

// not_analyzed evita mostrar "sin evidencia", que implicaría que sí se buscó.
const EMPTY_CATEGORY: CategoryData = {
  items: [],
  confidence: 0,
  source_references: [],
  extraction_status: "not_analyzed",
  summary: "Sin datos extraídos todavía.",
  is_reviewed: false,
};

interface CategoryListProps {
  analysis: AnalysisDetail;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

export function CategoryList({ analysis, onViewSource }: CategoryListProps) {
  const categories = analysis.current_version?.extracted_data ?? ({} as Record<CategoryId, CategoryData>);
  const summary = getAnalysisSummary(analysis);

  return (
    <section aria-label="Categorías de análisis" className="flex flex-col gap-3" data-testid="categories-tab-content">
      <div className="flex flex-wrap items-center gap-2 px-1" data-testid="categories-summary-strip">
        <span className="text-[13px] font-semibold text-[#003C6B]">{`${summary.extractedCategories}/8 categorías extraídas`}</span>
        {summary.conflict > 0 ? (
          <span className="inline-flex rounded-full bg-[#FEE2E2] px-2.5 py-1 text-[11px] font-bold text-[#DC2626]">
            {`${summary.conflict} ${summary.conflict === 1 ? "conflicto" : "conflictos"}`}
          </span>
        ) : null}
        {summary.notFound > 0 ? (
          <span className="inline-flex rounded-full bg-[rgba(169,102,255,.14)] px-2.5 py-1 text-[11px] font-bold text-[#6E2FC9]">
            {`${summary.notFound} ${summary.notFound === 1 ? "no encontrado" : "no encontrados"}`}
          </span>
        ) : null}
      </div>

      {CATEGORY_ORDER.map((categoryId) => (
        <CategorySection
          key={categoryId}
          analysisStatus={analysis.status}
          categoryId={categoryId}
          category={categories[categoryId] ?? EMPTY_CATEGORY}
          onViewSource={onViewSource}
        />
      ))}
    </section>
  );
}
