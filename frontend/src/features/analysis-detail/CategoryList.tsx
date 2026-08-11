import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CategorySection } from "./CategorySection";
import type { AnalysisDetail, CategoryData, CategoryId, Citation, NarrativeSource } from "./types";

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
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

export function CategoryList({ analysis, onViewSource }: CategoryListProps) {
  const categories = analysis.current_version?.extracted_data ?? ({} as Record<CategoryId, CategoryData>);

  return (
    <section aria-label="Categorías de análisis" className="divide-y divide-gray-100">
      {CATEGORY_ORDER.map((categoryId) => (
        <CategorySection
          key={categoryId}
          categoryId={categoryId}
          category={categories[categoryId] ?? EMPTY_CATEGORY}
          onViewSource={onViewSource}
        />
      ))}
    </section>
  );
}
