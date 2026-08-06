import { AlertTriangle } from "lucide-react";

import { Badge } from "../../components/Badge";
import { CATEGORY_ICONS, CATEGORY_NAMES, CRITICAL_CATEGORIES } from "../../utils/categoryIcons";
import { needsAction, sortFieldsBySeverity } from "../../utils/fieldSeverity";
import { NarrativeBlock } from "./components/NarrativeBlock";
import { FieldCard } from "./FieldCard";
import { FieldRow } from "./FieldRow";
import { FieldStateBadge } from "./FieldStateBadge";
import type { CategoryData, CategoryId, Citation } from "./types";
import { buildNarrativeSynthesis } from "./utils/narrativeSynthesis";
import { getCategoryCounts } from "./utils/categoryStats";

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
  const orderedFields = sortFieldsBySeverity(category.items);
  const actionableFields = orderedFields.filter(needsAction);
  const computedSynthesis = buildNarrativeSynthesis(category, categoryId);
  const synthesis = category.narrative?.trim()
    ? {
      ...computedSynthesis,
      text: category.narrative,
      intro: null,
      bullets: [],
      hasUsefulData: true,
    }
    : computedSynthesis;
  const allCitations = category.items.flatMap((item) => item.citations);
  const hasClickableEvidence = allCitations.some(
    (citation) => citation.document_id.trim() !== "" && citation.page > 0 && citation.text.trim() !== "",
  );
  const isReviewed = category.is_reviewed && hasClickableEvidence;

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
          {counts.extracted > 0 ? <Badge tone="success">{`${counts.extracted} extraídos`}</Badge> : null}
          {counts.notFound > 0 ? <Badge tone="warning">{`${counts.notFound} no encontrados`}</Badge> : null}
          {counts.conflict > 0 ? (
            <Badge tone="error" icon={AlertTriangle}>{`${counts.conflict} ${conflictWord}`}</Badge>
          ) : null}
          {counts.notApplicable > 0 ? <Badge tone="info">{`${counts.notApplicable} no aplica`}</Badge> : null}
          <FieldStateBadge state={state} />
        </div>
      </div>

      <NarrativeBlock synthesis={synthesis} citations={allCitations} onViewSource={onViewSource} />

      {actionableFields.length > 0 ? (
        <div className="mt-4">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-700">Acciones recomendadas</h4>
          <div className="space-y-2">
            {actionableFields.map((field) => (
              <FieldCard key={field.field_name} field={field} onViewSource={onViewSource} />
            ))}
          </div>
        </div>
      ) : null}

      {orderedFields.length > 0 ? (
        <details className="mt-4 rounded border border-gray-200 bg-white p-3" data-testid="category-details">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-gray-700">
            Detalle por campo ({orderedFields.length})
          </summary>
          <div className="mt-3 space-y-2">
            {orderedFields.map((field) => (
              <FieldRow key={`${field.field_name}-${field.field_state}`} field={field} onViewSource={onViewSource} />
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}
