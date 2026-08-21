import { AlertTriangle } from "lucide-react";

import { Badge } from "../../components/Badge";
import { CATEGORY_ICONS, CATEGORY_NAMES, CRITICAL_CATEGORIES } from "../../utils/categoryIcons";
import { getConfidenceLevel } from "../../utils/confidence";
import { NarrativeBlocks } from "./components/NarrativeBlocks";
import { PlazosTimeline } from "./components/PlazosTimeline";
import { FieldBadge } from "./FieldBadge";
import { FieldStateBadge } from "./FieldStateBadge";
import type { CategoryData, CategoryId, Citation } from "./types";
import { QualityNotice } from "./components/QualityNotice";
import { getCategoryCounts } from "./utils/categoryStats";
import { dedupeCitations } from "./utils/dedupeCitations";
import { buildNarrativeBlocks } from "./utils/narrativeSynthesis";
import { TrackingCommentsPanel } from "./components/TrackingCommentsPanel";
import type { TrackingCategoryStatus, TrackingItemStatus, TrackingCategory } from "../../types/tracking";

interface CategorySectionProps {
  analysisId?: string;
  categoryId: CategoryId;
  category: CategoryData;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
  trackingCategory?: TrackingCategory;
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
  trackingReadOnly?: boolean;
  trackingActionLoading?: boolean;
  trackingItemLoadingId?: string | null;
}

export function CategorySection({
  analysisId,
  categoryId,
  category,
  onViewSource,
  trackingCategory,
  onChangeTrackingStatus,
  onChangeTrackingItemStatus,
  onCreateTrackingComment,
  onUpdateTrackingComment,
  onDeleteTrackingComment,
  trackingReadOnly = false,
  trackingActionLoading = false,
  trackingItemLoadingId = null,
}: CategorySectionProps) {
  const isCritical = CRITICAL_CATEGORIES.has(categoryId);
  const Icon = CATEGORY_ICONS[categoryId];
  const name = CATEGORY_NAMES[categoryId];
  const counts = getCategoryCounts(category);
  const narrative = category.narrative ?? buildNarrativeBlocks(category, categoryId);
  const allCitations = dedupeCitations(category.items.flatMap((item) => item.citations));
  const hasClickableEvidence = allCitations.some(
    (citation) => citation.document_id.trim() !== "" && citation.page > 0 && citation.text.trim() !== "",
  );
  const isReviewed = category.is_reviewed && hasClickableEvidence;
  const confidenceLevel = category.confidence > 0 ? getConfidenceLevel(category.confidence) : null;
  const categoryFullyNotApplicable =
    category.extraction_status === "not_applicable" && counts.extracted === 0 && counts.conflict === 0;

  const state = category.extraction_status === "not_analyzed"
    // CTX-03: fuera del alcance del análisis. No es un hallazgo sobre el pliego.
    ? "no_analizada"
    : category.extraction_status === "failed"
    ? "error"
    // Solo marcar como "no_aplica" si NO hay items extraídos (para evitar badge inconsistente)
    : categoryFullyNotApplicable
      ? "no_aplica"
      : counts.conflict > 0
        ? "con_conflictos"
        : isReviewed
          ? "revisada"
          : isCritical
            ? "critica"
            : "sin_revisar";

  let accentClass = "border-l-gray-200";
  if (counts.conflict > 0) {
    accentClass = "border-l-error";
  } else if (isCritical && !isReviewed) {
    accentClass = "border-l-highlight";
  } else if (isReviewed) {
    accentClass = "border-l-success";
  }

  const conflictWord = counts.conflict === 1 ? "conflicto" : "conflictos";
  const shouldShowComplianceSummary = Boolean(
    trackingCategory &&
      trackingCategory.items.length > 0 &&
      (trackingReadOnly || trackingCategory.status === "closed"),
  );

  const complianceStats = trackingCategory
    ? trackingCategory.items.reduce(
        (acc, item) => {
          if (item.status === "compliant") {
            acc.compliant += 1;
          } else if (item.status === "non_compliant") {
            acc.nonCompliant += 1;
          } else if (item.status === "not_evaluated") {
            acc.notEvaluated += 1;
          } else if (item.status === "not_applicable") {
            acc.notApplicable += 1;
          }

          return acc;
        },
        { compliant: 0, nonCompliant: 0, notEvaluated: 0, notApplicable: 0 },
      )
    : { compliant: 0, nonCompliant: 0, notEvaluated: 0, notApplicable: 0 };

  const totalTrackingItems =
    complianceStats.compliant +
    complianceStats.nonCompliant +
    complianceStats.notEvaluated +
    complianceStats.notApplicable;
  const compliancePercentage =
    totalTrackingItems > 0
      ? Math.round(((complianceStats.compliant + complianceStats.notApplicable) / totalTrackingItems) * 100)
      : 0;
  const complianceToneClass =
    compliancePercentage >= 80
      ? "text-success"
      : compliancePercentage >= 50
        ? "text-warning"
        : "text-error";

  return (
    <article id={`category-${categoryId}`} className={`border-l-4 py-5 pl-4 ${accentClass}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon data-icon={Icon.displayName ?? Icon.name} className="h-5 w-5 text-gray-700" aria-hidden="true" />
          <h3 className="font-semibold text-gray-900">{name}</h3>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {confidenceLevel ? <FieldBadge level={confidenceLevel} /> : null}
          {counts.extracted > 0 ? (
            <Badge
              tone="success"
              title="Cantidad de datos extraídos por esta categoría"
              className="normal-case px-1.5 py-0.5 text-[10px] font-medium opacity-80"
            >
              {`${counts.extracted} extraídos`}
            </Badge>
          ) : null}
          {counts.notFound > 0 ? <Badge tone="warning">{`${counts.notFound} no encontrados`}</Badge> : null}
          {counts.conflict > 0 ? (
            <Badge tone="error" icon={AlertTriangle}>{`${counts.conflict} ${conflictWord}`}</Badge>
          ) : null}
          {categoryFullyNotApplicable && counts.notApplicable > 0 ? (
            <Badge tone="info">{`${counts.notApplicable} no aplica`}</Badge>
          ) : null}
          {state !== "sin_revisar" && state !== "critica" ? <FieldStateBadge state={state} /> : null}
        </div>
      </div>

      {shouldShowComplianceSummary ? (
        <div
          className="mt-2 rounded-sm border border-gray-200/70 bg-gray-50/70 px-3 py-2 text-xs text-gray-700"
          data-testid="category-compliance-summary"
        >
          <p className="text-sm font-semibold text-gray-800">
            <span>Cumplimiento </span>
            <span className={complianceToneClass}>{`${compliancePercentage}%`}</span>
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className="font-medium text-gray-600">{`${complianceStats.compliant} cumplen`}</span>
            <span className="font-medium text-gray-600">{`${complianceStats.nonCompliant} no cumplen`}</span>
            <span className="font-medium text-gray-600">{`${complianceStats.notEvaluated} sin evaluar`}</span>
            <span className="font-medium text-gray-600">{`${complianceStats.notApplicable} no aplica`}</span>
          </p>
        </div>
      ) : null}

      <QualityNotice quality={category.quality} />

      {categoryId === "plazos_clave" ? (
        <PlazosTimeline
          items={category.items}
          narrativeSources={narrative.sources}
          onViewSource={onViewSource}
        />
      ) : (
        <NarrativeBlocks
          narrative={narrative}
          onViewSource={onViewSource}
          trackingItems={trackingCategory?.items}
          isTrackingClosed={trackingReadOnly || trackingCategory?.status === "closed"}
          loadingTrackingItemId={trackingItemLoadingId}
          onChangeTrackingItemStatus={(trackingItemId, status) =>
            onChangeTrackingItemStatus?.(categoryId, trackingItemId, status)
          }
        />
      )}

      {trackingCategory && onCreateTrackingComment && (!trackingReadOnly || trackingCategory.comments_count > 0) ? (
        <TrackingCommentsPanel
          analysisId={analysisId}
          category={trackingCategory}
          isClosed={trackingReadOnly || trackingCategory.status === "closed"}
          loading={trackingActionLoading}
          isReadOnly={trackingReadOnly}
          onCreateComment={async ({ content }) => {
            await onCreateTrackingComment({ categoryKey: categoryId, content });
          }}
          onUpdateComment={async ({ commentId, content }) => {
            await onUpdateTrackingComment?.({ categoryKey: categoryId, commentId, content });
          }}
          onDeleteComment={async ({ commentId }) => {
            await onDeleteTrackingComment?.({ categoryKey: categoryId, commentId });
          }}
        />
      ) : null}
    </article>
  );
}
