import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CategoryAccordion } from "./CategoryAccordion";
import type { AnalysisDetail, CategoryData, CategoryId, Citation } from "./types";

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

  return (
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
  );
}
