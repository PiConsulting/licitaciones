import { ChevronDown } from "lucide-react";

import { CATEGORY_ICONS, CATEGORY_NAMES, CRITICAL_CATEGORIES } from "../../utils/categoryIcons";
import { sortFieldsBySeverity } from "../../utils/fieldSeverity";
import { CategoryContent } from "./CategoryContent";
import { CategoryHeader } from "./CategoryHeader";
import { useAccordionState } from "./hooks/useAccordionState";
import type { CategoryData, CategoryId, Citation } from "./types";
import { getCategoryCounts } from "./utils/categoryStats";

interface CategoryAccordionProps {
  categoryId: CategoryId;
  category: CategoryData;
  onViewSource?: (payload: { citation: Citation; citations: Citation[] }) => void;
}

export function CategoryAccordion({ categoryId, category, onViewSource }: CategoryAccordionProps) {
  const { expandedCategories, toggleCategory } = useAccordionState();
  const isOpen = expandedCategories.includes(categoryId);

  const isCritical = CRITICAL_CATEGORIES.has(categoryId);
  const Icon = CATEGORY_ICONS[categoryId];
  const name = CATEGORY_NAMES[categoryId];

  const counts = getCategoryCounts(category);

  let borderClass = "border-l-4 border-l-gray-200 bg-white";
  if (counts.conflict > 0) {
    borderClass = "border-l-4 border-l-error bg-white";
  } else if (isCritical && !category.is_reviewed) {
    borderClass = "border-l-4 border-l-highlight bg-highlight-light";
  } else if (category.is_reviewed) {
    borderClass = "border-l-4 border-l-success bg-success-light";
  }

  return (
    <article id={`category-${categoryId}`} className={`mb-4 rounded-md ${borderClass}`}>
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        onClick={() => toggleCategory(categoryId)}
        aria-expanded={isOpen}
        aria-controls={`category-content-${categoryId}`}
      >
        <CategoryHeader
          icon={Icon}
          name={name}
          isCritical={isCritical}
          isReviewed={category.is_reviewed}
          extractionStatus={category.extraction_status}
          extractedCount={counts.extracted}
          notFoundCount={counts.notFound}
          conflictCount={counts.conflict}
          notApplicableCount={counts.notApplicable}
        />
        <ChevronDown className={`h-5 w-5 text-gray-500 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen ? (
        <div className="px-4 pb-4 pt-2 duration-200">
          <CategoryContent
            summary={category.summary}
            sourceReferences={category.source_references}
            fields={sortFieldsBySeverity(category.items)}
            categoryId={categoryId}
            onViewSource={onViewSource}
          />
        </div>
      ) : null}
    </article>
  );
}
