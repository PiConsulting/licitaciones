import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Check, X, Ban } from "lucide-react";

import { CompleteTrackingConfirmModal } from "../../components/analysis/CompleteTrackingConfirmModal";
import { useToast } from "../../components/ToastContainer";
import { CATEGORY_ORDER } from "../../utils/categoryIcons";
import { useAnalysisDetail } from "../analysis-detail/hooks/useAnalysisDetail";
import {
  useCompleteTracking,
  useCreateTrackingComment,
  useDeleteTrackingComment,
  useStartTracking,
  useUpdateTrackingCategoryStatus,
  useUpdateTrackingComment,
  useUpdateTrackingItemStatus,
} from "../analysis-detail/hooks/useTrackingMutations";
import { ComplianceFilters, ComplianceOverview, type TrackingFilter } from "../analysis-detail/components/TrackingProgressSummary";
import { getFieldValue } from "../analysis-detail/utils/analysisFields";
import { ChecklistCategoryCard } from "./ChecklistCategoryCard";

export function ChecklistPage() {
  const { analysisId } = useParams();
  const { addToast } = useToast();

  const query = useAnalysisDetail(analysisId ?? "");
  const completeTrackingMutation = useCompleteTracking();
  const startTrackingMutation = useStartTracking();
  const updateCategoryMutation = useUpdateTrackingCategoryStatus();
  const updateItemMutation = useUpdateTrackingItemStatus();
  const createCommentMutation = useCreateTrackingComment();
  const updateCommentMutation = useUpdateTrackingComment();
  const deleteCommentMutation = useDeleteTrackingComment();

  const [filter, setFilter] = useState<TrackingFilter>("all");
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({});
  const [showCompleteModal, setShowCompleteModal] = useState(false);

  const resumeTracking = startTrackingMutation.mutateAsync;
  useEffect(() => {
    const handleResumeTracking = () => {
      if (!analysisId) {
        return;
      }
      resumeTracking({ analysisId })
        .then(() => addToast("success", "Seguimiento reanudado correctamente."))
        .catch(() => addToast("error", "No se pudo reanudar el seguimiento."));
    };
    window.addEventListener("checklist:resume-tracking", handleResumeTracking);
    return () => window.removeEventListener("checklist:resume-tracking", handleResumeTracking);
  }, [analysisId, resumeTracking, addToast]);

  useEffect(() => {
    const handleCompleteTracking = () => setShowCompleteModal(true);
    window.addEventListener("checklist:complete-tracking", handleCompleteTracking);
    return () => window.removeEventListener("checklist:complete-tracking", handleCompleteTracking);
  }, []);

  if (!analysisId) {
    return <p className="text-sm text-error">ID de análisis inválido.</p>;
  }

  if (query.isLoading) {
    return <p className="text-sm text-gray-600">Cargando checklist...</p>;
  }

  if (query.isError || !query.data) {
    return <p className="text-sm text-error">No se pudo cargar el checklist.</p>;
  }

  const analysis = query.data;
  const tracking = analysis.tracking;

  if (!tracking) {
    return <p className="text-sm text-gray-600">Este análisis todavía no tiene un seguimiento iniciado.</p>;
  }

  const isReadOnly = tracking.status === "completed";
  const actionLoading =
    updateCategoryMutation.isPending ||
    updateItemMutation.isPending ||
    createCommentMutation.isPending ||
    updateCommentMutation.isPending ||
    deleteCommentMutation.isPending;

  const categoriesData = analysis.current_version.extracted_data;
  const checklistCategories = tracking.categories.filter((category) => category.category_key !== "objeto_alcance");
  const checklistTracking = {
    ...tracking,
    categories: checklistCategories,
    summary: {
      ...tracking.summary,
      total_categories: checklistCategories.length,
      not_reviewed: checklistCategories.filter((category) => category.status === "not_reviewed").length,
      in_review: checklistCategories.filter((category) => category.status === "in_review").length,
      closed: checklistCategories.filter((category) => category.status === "closed").length,
    },
  };
  const trackingByKey = new Map(checklistCategories.map((category) => [category.category_key, category]));

  const filteredCategoryIds = CATEGORY_ORDER.filter((categoryId) => {
    const trackingCategory = trackingByKey.get(categoryId);
    if (!trackingCategory) {
      return false;
    }
    const hasPending = trackingCategory.items.some((item) => item.status === "not_evaluated");
    const hasNonCompliant = trackingCategory.items.some((item) => item.status === "non_compliant");
    const closed = trackingCategory.status === "closed";
    if (filter === "pending") {
      return hasPending && !closed;
    }
    if (filter === "issues") {
      return hasNonCompliant;
    }
    if (filter === "closed") {
      return closed;
    }
    return true;
  });

  const isOpen = (categoryId: string, trackingCategoryStatus: string) =>
    openCategories[categoryId] ?? trackingCategoryStatus !== "closed";

  const startedAtLabel = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(
    new Date(tracking.started_at),
  );
  const startedByLabel = (tracking.started_by_name ?? tracking.started_by ?? "").trim();
  const organismo = getFieldValue(analysis, "datos_procedimiento", "Organismo convocante");
  const subtitleParts = [analysis.analysis_name, organismo ?? analysis.business_unit].filter(Boolean).join(" · ");

  const handleComplete = async () => {
    try {
      await completeTrackingMutation.mutateAsync({ analysisId });
      addToast("success", "Seguimiento finalizado. Queda en modo solo lectura; podés reanudarlo si necesitás editarlo.");
      setShowCompleteModal(false);
    } catch {
      addToast("error", "No se pudo finalizar el seguimiento.");
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[26px] font-bold leading-[1.15] tracking-[-0.015em] text-[#003C6B]">
            Checklist de cumplimiento
          </h1>
          <p className="mt-1.5 text-sm text-[rgba(0,60,107,.68)]">
            {subtitleParts ? <span className="font-semibold">{subtitleParts}</span> : null}
            {startedByLabel ? ` · iniciado ${startedAtLabel} por ${startedByLabel}` : ` · iniciado ${startedAtLabel}`}
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-3 text-xs text-[rgba(0,60,107,.68)]">
            <span className="inline-flex items-center gap-1.5">
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-[#1FC9A8] text-[#003C6B]">
                <Check className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
              </span>
              Cumple
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-[#DC2626] text-white">
                <X className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
              </span>
              No cumple
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-[#003C6B] text-white">
                <Ban className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
              </span>
              No aplica
            </span>
          </div>
        </div>

        <ComplianceFilters tracking={checklistTracking} filter={filter} onFilterChange={setFilter} />
      </section>

      <ComplianceOverview tracking={checklistTracking} />

      <section aria-label="Categorías" className="flex flex-col gap-3">
        {filteredCategoryIds.map((categoryId) => {
          const trackingCategory = trackingByKey.get(categoryId);
          if (!trackingCategory) {
            return null;
          }
          return (
            <ChecklistCategoryCard
              key={categoryId}
              analysisId={analysisId}
              categoryId={categoryId}
              category={categoriesData[categoryId] ?? { items: [], confidence: 0, source_references: [], extraction_status: "not_analyzed", summary: "", is_reviewed: false }}
              trackingCategory={trackingCategory}
              isOpen={isOpen(categoryId, trackingCategory.status)}
              readOnly={isReadOnly}
              actionLoading={actionLoading}
              onToggleOpen={() =>
                setOpenCategories((current) => ({
                  ...current,
                  [categoryId]: !isOpen(categoryId, trackingCategory.status),
                }))
              }
              onToggleClosed={() => {
                const nextStatus = trackingCategory.status === "closed" ? "in_review" : "closed";
                void updateCategoryMutation
                  .mutateAsync({ analysisId, categoryKey: categoryId, status: nextStatus })
                  .then(() => addToast("success", "Estado de categoría actualizado."))
                  .catch(() => addToast("error", "No se pudo actualizar el estado de la categoría."));
              }}
              onChangeItemStatus={(trackingItemId, status) => {
                void updateItemMutation.mutateAsync({ analysisId, categoryKey: categoryId, trackingItemId, status });
              }}
              onCreateComment={async (trackingItemId, content) => {
                await createCommentMutation.mutateAsync({ analysisId, categoryKey: categoryId, trackingItemId, content });
                addToast("success", "Comentario guardado.");
              }}
              onUpdateComment={async (commentId, content) => {
                await updateCommentMutation.mutateAsync({ analysisId, categoryKey: categoryId, commentId, content });
                addToast("success", "Comentario actualizado.");
              }}
              onDeleteComment={async (commentId) => {
                await deleteCommentMutation.mutateAsync({ analysisId, categoryKey: categoryId, commentId });
                addToast("success", "Comentario eliminado.");
              }}
            />
          );
        })}
      </section>

      {showCompleteModal ? (
        <CompleteTrackingConfirmModal
          isSubmitting={completeTrackingMutation.isPending}
          onCancel={() => setShowCompleteModal(false)}
          onConfirm={() => {
            void handleComplete();
          }}
        />
      ) : null}
    </div>
  );
}
