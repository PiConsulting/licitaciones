import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { CategorySection } from "./CategorySection";
import type { AnalysisDetail, CategoryData, CategoryId, Citation, NarrativeSource } from "./types";
import type { TrackingCategoryStatus, TrackingItemStatus } from "../../types/tracking";

// Categoría que todavía no corrió (típicamente fase 2, mientras el análisis
// está en "en_revision" recién con fase 1 completa): `extraction_status:
// "not_analyzed"` hace que `CategorySection` la muestre en minimalista
// ("Todavía no fue analizada") en vez del contenedor completo de "Respuesta"
// con "No se encontró información" / "Sin evidencia clickeable" -- ese texto
// afirma que se buscó y no se encontró nada, cuando en realidad todavía no se
// buscó nada.
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
}: CategoryListProps) {
  const categories = analysis.current_version?.extracted_data ?? ({} as Record<CategoryId, CategoryData>);
  const trackingByCategory = new Map((analysis.tracking?.categories ?? []).map((category) => [category.category_key, category]));
  const trackingReadOnly = analysis.tracking?.status === "completed";

  return (
    <section aria-label="Categorías de análisis" className="divide-y divide-slate-200/70">
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
        />
      ))}
    </section>
  );
}
