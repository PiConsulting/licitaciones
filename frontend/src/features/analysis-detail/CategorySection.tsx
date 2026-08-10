import { AlertTriangle } from "lucide-react";

import { Badge } from "../../components/Badge";
import { CATEGORY_ICONS, CATEGORY_NAMES, CRITICAL_CATEGORIES } from "../../utils/categoryIcons";
import { getConfidenceLevel } from "../../utils/confidence";
import { NarrativeBlocks } from "./components/NarrativeBlocks";
import { PlazosTimeline } from "./components/PlazosTimeline";
import { FieldBadge } from "./FieldBadge";
import { FieldStateBadge } from "./FieldStateBadge";
import type { CategoryData, CategoryId, Citation } from "./types";
import { getCategoryCounts } from "./utils/categoryStats";
import { dedupeCitations } from "./utils/dedupeCitations";
import { buildNarrativeBlocks } from "./utils/narrativeSynthesis";

interface CategorySectionProps {
  categoryId: CategoryId;
  category: CategoryData;
  onViewSource?: (payload: { citation: Citation; citations: Citation[] }) => void;
}

export function CategorySection({ categoryId, category, onViewSource }: CategorySectionProps) {
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

  const state = category.extraction_status === "failed"
    ? "error"
    : category.extraction_status === "not_applicable"
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

  return (
    <article id={`category-${categoryId}`} className={`border-l-4 py-5 pl-4 ${accentClass}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon data-icon={Icon.displayName ?? Icon.name} className="h-5 w-5 text-gray-700" aria-hidden="true" />
          <h3 className="font-semibold text-gray-900">{name}</h3>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {confidenceLevel ? <FieldBadge level={confidenceLevel} /> : null}
          {counts.extracted > 0 ? <Badge tone="success">{`${counts.extracted} extraídos`}</Badge> : null}
          {counts.notFound > 0 ? <Badge tone="warning">{`${counts.notFound} no encontrados`}</Badge> : null}
          {counts.conflict > 0 ? (
            <Badge tone="error" icon={AlertTriangle}>{`${counts.conflict} ${conflictWord}`}</Badge>
          ) : null}
          {categoryFullyNotApplicable && counts.notApplicable > 0 ? (
            <Badge tone="info">{`${counts.notApplicable} no aplica`}</Badge>
          ) : null}
          {state !== "sin_revisar" ? <FieldStateBadge state={state} /> : null}
        </div>
      </div>

      {categoryId === "plazos_clave" ? (
        <PlazosTimeline items={category.items} onViewSource={onViewSource} />
      ) : (
        <NarrativeBlocks narrative={narrative} onViewSource={onViewSource} />
      )}
    </article>
  );
}
