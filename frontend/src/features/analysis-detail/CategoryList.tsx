import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CategorySection } from "./CategorySection";
import type { AnalysisDetail, CategoryData, CategoryId, Citation, NarrativeSource } from "./types";
import type { TrackingCategoryStatus, TrackingItemStatus } from "../../types/tracking";

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
  onChangeTrackingStatus?: (categoryKey: string, status: TrackingCategoryStatus) => void;
  onChangeTrackingItemStatus?: (categoryKey: string, trackingItemId: string, status: TrackingItemStatus) => void;
  onCreateTrackingComment?: (payload: {
    categoryKey: string;
    content: string;
  }) => Promise<void>;
  onUpdateTrackingComment?: (payload: {
    categoryKey: string;
    commentId: string;
    content: string;
  }) => Promise<void>;
  onDeleteTrackingComment?: (payload: { categoryKey: string; commentId: string }) => Promise<void>;
  trackingActionLoading?: boolean;
  trackingItemLoadingId?: string | null;
}

export function CategoryList({
  analysis,
  onViewSource,
  onChangeTrackingStatus,
  onChangeTrackingItemStatus,
  onCreateTrackingComment,
  onUpdateTrackingComment,
  onDeleteTrackingComment,
  trackingActionLoading = false,
  trackingItemLoadingId = null,
}: CategoryListProps) {
  const categories = analysis.current_version?.extracted_data ?? ({} as Record<CategoryId, CategoryData>);
  const trackingByCategory = new Map((analysis.tracking?.categories ?? []).map((category) => [category.category_key, category]));
  const trackingReadOnly = analysis.tracking?.status === "completed";

  return (
    <section aria-label="Categorías de análisis" className="divide-y-2 divide-slate-300">
      {CATEGORY_ORDER.map((categoryId) => (
        <CategorySection
          key={categoryId}
          analysisId={analysis.id}
          categoryId={categoryId}
          category={categories[categoryId] ?? EMPTY_CATEGORY}
          onViewSource={onViewSource}
          trackingCategory={trackingByCategory.get(categoryId)}
          onChangeTrackingStatus={onChangeTrackingStatus}
          onChangeTrackingItemStatus={onChangeTrackingItemStatus}
          onCreateTrackingComment={onCreateTrackingComment}
          onUpdateTrackingComment={onUpdateTrackingComment}
          onDeleteTrackingComment={onDeleteTrackingComment}
          trackingReadOnly={trackingReadOnly}
          trackingActionLoading={trackingActionLoading}
          trackingItemLoadingId={trackingItemLoadingId}
        />
      ))}
    </section>
  );
}
