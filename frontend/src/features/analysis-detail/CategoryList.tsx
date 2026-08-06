import { useEffect } from "react";

import { Button } from "../../components/Button";
import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CategoryAccordion } from "./CategoryAccordion";
import { useAccordionState } from "./hooks/useAccordionState";
import type { AnalysisDetail, CategoryData, CategoryId, Citation } from "./types";
import { getAnalysisSummary } from "./utils/categoryStats";

const EMPTY_CATEGORY: CategoryData = {
  items: [],
  confidence: 0,
  source_references: [],
  extraction_status: "partial",
  summary: "Sin datos extraídos todavía.",
  is_reviewed: false,
};

interface CategoryListProps {
  analysis: AnalysisDetail;
  onViewSource?: (payload: { citation: Citation; citations: Citation[] }) => void;
}

export function CategoryList({ analysis, onViewSource }: CategoryListProps) {
  const categories = analysis.current_version?.extracted_data ?? ({} as Record<CategoryId, CategoryData>);
  const { expandAll, collapseAll, initializeDefaults } = useAccordionState();

  useEffect(() => {
    const { categoriesNeedingReview } = getAnalysisSummary(analysis);
    initializeDefaults(categoriesNeedingReview);
    // Only re-run when the analysis identity changes, not on every re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis.id]);

  return (
    <div>
      <div className="mb-2 flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={expandAll}>
          Expandir todo
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={collapseAll}>
          Colapsar todo
        </Button>
      </div>

      <section aria-label="Categorías de análisis" className="space-y-2">
        {CATEGORY_ORDER.map((categoryId) => (
          <CategoryAccordion
            key={categoryId}
            categoryId={categoryId}
            category={categories[categoryId] ?? EMPTY_CATEGORY}
            onViewSource={onViewSource}
          />
        ))}
      </section>
    </div>
  );
}
