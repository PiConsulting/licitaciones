import { CATEGORY_ICONS, CATEGORY_NAMES, CRITICAL_CATEGORIES } from "../../utils/categoryIcons";
import { getConfidenceLevel } from "../../utils/confidence";
import { NarrativeBlocks } from "./components/NarrativeBlocks";
import { PlazosTimeline } from "./components/PlazosTimeline";
import type { CategoryData, CategoryId, Citation, NarrativeSource } from "./types";
import { QualityNotice } from "./components/QualityNotice";
import { getCategoryCounts } from "./utils/categoryStats";
import { dedupeCitations } from "./utils/dedupeCitations";
import { buildNarrativeBlocks } from "./utils/narrativeSynthesis";

interface CategorySectionProps {
  analysisStatus?: "draft" | "queued" | "processing" | "en_revision" | "analyzed" | "validated" | "error" | "cancelled";
  categoryId: CategoryId;
  category: CategoryData;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

export function CategorySection({ analysisStatus, categoryId, category, onViewSource }: CategorySectionProps) {
  const isCritical = CRITICAL_CATEGORIES.has(categoryId);
  const Icon = CATEGORY_ICONS[categoryId];
  const name = CATEGORY_NAMES[categoryId];
  const counts = getCategoryCounts(category);
  const narrative = category.narrative ?? buildNarrativeBlocks(category, categoryId);
  const narrativeBullets = narrative.blocks.flatMap((block) => (block.type === "bullet_list" ? block.items : []));
  const allCitations = dedupeCitations(category.items.flatMap((item) => item.citations));
  const hasClickableEvidence = allCitations.some(
    (citation) => citation.document_id.trim() !== "" && citation.page > 0 && citation.text.trim() !== "",
  );
  const isReviewed = category.is_reviewed && hasClickableEvidence;
  const confidenceLevel = category.confidence > 0 ? getConfidenceLevel(category.confidence) : null;
  const confidenceLabel =
    confidenceLevel === "high" ? "Alta" : confidenceLevel === "medium" ? "Media" : confidenceLevel === "low" ? "Baja" : null;
  const isOnlyPhaseOneCategory = categoryId === "objeto_alcance";
  const hasRealExtraction = counts.extracted > 0 || counts.conflict > 0 || counts.notApplicable > 0;
  const isLegacyPendingCategoryInRevision =
    analysisStatus === "en_revision" &&
    !isOnlyPhaseOneCategory &&
    !hasRealExtraction;
  const isPhaseOnePendingEmptyCategory =
    category.extraction_status === "not_found" &&
    category.items.length === 0 &&
    category.confidence === 0 &&
    !category.is_reviewed;
  const isNotAnalyzedState =
    category.extraction_status === "not_analyzed" ||
    isPhaseOnePendingEmptyCategory ||
    isLegacyPendingCategoryInRevision;
  const categoryFullyNotApplicable =
    category.extraction_status === "not_applicable" && counts.extracted === 0 && counts.conflict === 0;

  const state = isNotAnalyzedState
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

  const accentColor =
    categoryId === "objeto_alcance"
      ? "#1FC9A8"
      : isCritical
        ? "#DC2626"
        : "#0099DB";

  const conflictWord = counts.conflict === 1 ? "conflicto" : "conflictos";

  const statusBadges: Array<{ text: string; className: string }> = [];

  if (confidenceLabel) {
    statusBadges.push({
      text: confidenceLabel,
      className:
        confidenceLevel === "high"
          ? "bg-[rgba(127,243,222,.35)] text-[#0B6B58]"
          : confidenceLevel === "medium"
            ? "bg-[rgba(169,102,255,.14)] text-[#6E2FC9]"
            : "bg-[#FEF3C7] text-[#B45309]",
    });
  }

  if (counts.extracted > 0) {
    statusBadges.push({
      text: `${counts.extracted} extraídos`,
      className: "bg-[rgba(0,153,219,.12)] text-[#0077AD]",
    });
  }

  if (isReviewed) {
    statusBadges.push({
      text: "Revisada",
      className: "bg-[rgba(127,243,222,.35)] text-[#0B6B58]",
    });
  }

  if (counts.notFound > 0) {
    statusBadges.push({
      text: `${counts.notFound} no encontrados`,
      className: "bg-[rgba(169,102,255,.14)] text-[#6E2FC9]",
    });
  }

  if (counts.conflict > 0) {
    statusBadges.push({
      text: `${counts.conflict} ${conflictWord}`,
      className: "bg-[#FEE2E2] text-[#DC2626]",
    });
  }

  if (categoryFullyNotApplicable && counts.notApplicable > 0) {
    statusBadges.push({
      text: `${counts.notApplicable} no aplica`,
      className: "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]",
    });
  }

  if (state === "error") {
    statusBadges.push({
      text: "Error",
      className: "bg-[#FEE2E2] text-[#DC2626]",
    });
  }

  if (state === "no_analizada") {
    statusBadges.push({
      text: "No analizada",
      className: "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]",
    });
  }

  return (
    <article
      id={`category-${categoryId}`}
      className="flex overflow-hidden rounded-2xl border border-[rgba(0,60,107,.12)] bg-white"
      data-testid="category-card"
    >
      <div
        className="w-1 shrink-0"
        style={{ backgroundColor: accentColor }}
        data-testid="category-accent"
        data-accent-tone={accentClass}
      />

      <div className="flex min-w-0 flex-1 flex-col gap-3 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-[#F4F9FC] text-[#003C6B]">
              <Icon data-icon={Icon.displayName ?? Icon.name} className="h-4 w-4" aria-hidden="true" />
            </span>
            <h3 className="text-base font-semibold text-[#003C6B] [font-family:'Space_Grotesk',sans-serif]">{name}</h3>
            {isCritical ? (
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#2F4EF8]">Crítica</span>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {statusBadges.map((badge) => (
              <span
                key={badge.text}
                className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${badge.className}`}
              >
                {badge.text}
              </span>
            ))}
          </div>
        </div>

        <QualityNotice quality={category.quality} />

        {state === "no_analizada" ? (
          // A propósito minimalista: "sin evidencia" implicaría que se buscó, pero fase 2 no corrió.
          <p className="text-[13px] text-[rgba(0,60,107,.55)]" data-testid="category-not-analyzed">
            Todavía no fue analizada. Se completa al analizar las categorías restantes.
          </p>
        ) : categoryId === "plazos_clave" ? (
          <PlazosTimeline
            items={category.items}
            narrativeSources={narrative.sources}
            narrativeBullets={narrativeBullets}
            onViewSource={onViewSource}
          />
        ) : (
          <NarrativeBlocks narrative={narrative} onViewSource={onViewSource} />
        )}
      </div>
    </article>
  );
}
