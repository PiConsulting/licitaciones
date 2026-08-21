import { Badge } from "../../../components/Badge";
import { CATEGORY_ORDER, CATEGORY_NAMES } from "../../../utils/categoryIcons";
import type { AnalysisTracking, TrackingCategoryStatus } from "../../../types/tracking";
import type { CategoryId } from "../types";

interface TrackingProgressSummaryProps {
  tracking: AnalysisTracking;
}

const LABELS: Record<TrackingCategoryStatus, string> = {
  not_reviewed: "Disponibles",
  in_review: "Editables",
  closed: "Terminadas",
};

export function TrackingProgressSummary({ tracking }: TrackingProgressSummaryProps) {
  const summary = tracking.summary;
  const isCompleted = tracking.status === "completed";

  const categoryByStatus = (status: TrackingCategoryStatus) =>
    tracking.categories
      .filter((category) => category.status === status)
      .sort(
        (a, b) =>
          CATEGORY_ORDER.indexOf(a.category_key as CategoryId) - CATEGORY_ORDER.indexOf(b.category_key as CategoryId),
      );

  const handleScrollToFirst = (status: TrackingCategoryStatus) => {
    const target = categoryByStatus(status)[0];
    if (!target) {
      return;
    }
    const element = document.getElementById(`category-${target.category_key}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section aria-label="Progreso de seguimiento" aria-live="polite" className="mb-4 rounded-md border border-gray-200 bg-gray-50 p-3">
      {isCompleted ? (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <p className="text-sm font-semibold text-gray-900">Seguimiento finalizado</p>
          <Badge tone="neutral">Solo lectura</Badge>
        </div>
      ) : (
        <>
          <p className="text-sm font-semibold text-gray-900">{`${summary.closed} de ${summary.total_categories} categorías terminadas - ${summary.closed_percentage}%`}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <button type="button" className="rounded" onClick={() => handleScrollToFirst("not_reviewed")}>
              <Badge tone="neutral">{`${LABELS.not_reviewed}: ${summary.not_reviewed}`}</Badge>
            </button>
            <button type="button" className="rounded" onClick={() => handleScrollToFirst("in_review")}>
              <Badge tone="highlight">{`${LABELS.in_review}: ${summary.in_review}`}</Badge>
            </button>
            <button type="button" className="rounded" onClick={() => handleScrollToFirst("closed")}>
              <Badge tone="success">{`${LABELS.closed}: ${summary.closed}`}</Badge>
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            {tracking.categories
              .filter((category) => category.status === "not_reviewed")
              .slice(0, 2)
              .map((category) => CATEGORY_NAMES[category.category_key as CategoryId])
              .join(" · ")}
          </p>
        </>
      )}
    </section>
  );
}
