import { CATEGORY_ORDER, CRITICAL_CATEGORIES } from "../../../utils/categoryIcons";
import type { AnalysisDetail, CategoryData, CategoryId } from "../types";

export interface CategoryCounts {
  extracted: number;
  notFound: number;
  conflict: number;
  notApplicable: number;
  total: number;
}

export function getCategoryCounts(category: CategoryData): CategoryCounts {
  return {
    extracted: category.items.filter((field) => field.field_state === "extraido").length,
    notFound: category.items.filter((field) => field.field_state === "no_encontrado").length,
    conflict: category.items.filter((field) => field.field_state === "en_conflicto").length,
    notApplicable: category.items.filter((field) => field.field_state === "no_aplica").length,
    total: category.items.length,
  };
}

export interface AnalysisSummary {
  totalFields: number;
  extracted: number;
  notFound: number;
  conflict: number;
  notApplicable: number;
  categoriesNeedingReview: CategoryId[];
}

export function getAnalysisSummary(analysis: AnalysisDetail): AnalysisSummary {
  const categories = analysis.current_version?.extracted_data ?? ({} as Record<CategoryId, CategoryData>);

  const summary: AnalysisSummary = {
    totalFields: 0,
    extracted: 0,
    notFound: 0,
    conflict: 0,
    notApplicable: 0,
    categoriesNeedingReview: [],
  };

  for (const categoryId of CATEGORY_ORDER) {
    const category = categories[categoryId];
    if (!category) {
      continue;
    }

    const counts = getCategoryCounts(category);
    summary.totalFields += counts.total;
    summary.extracted += counts.extracted;
    summary.notFound += counts.notFound;
    summary.conflict += counts.conflict;
    summary.notApplicable += counts.notApplicable;

    const isCriticalUnreviewed = CRITICAL_CATEGORIES.has(categoryId) && !category.is_reviewed;
    if (counts.conflict > 0 || isCriticalUnreviewed) {
      summary.categoriesNeedingReview.push(categoryId);
    }
  }

  return summary;
}
