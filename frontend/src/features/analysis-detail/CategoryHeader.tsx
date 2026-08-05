import type { LucideIcon } from "lucide-react";

import { FieldStateBadge } from "./FieldStateBadge";

interface CategoryHeaderProps {
  icon: LucideIcon;
  name: string;
  isCritical: boolean;
  isReviewed: boolean;
  extractionStatus: "success" | "partial" | "failed" | "not_found" | "not_applicable";
  extractedCount: number;
  notFoundCount: number;
  conflictCount: number;
}

export function CategoryHeader({
  icon: Icon,
  name,
  isCritical,
  isReviewed,
  extractionStatus,
  extractedCount,
  notFoundCount,
  conflictCount,
}: CategoryHeaderProps) {
  const state = extractionStatus === "failed"
    ? "error"
    : extractionStatus === "not_applicable"
      ? "no_aplica"
      : conflictCount > 0
        ? "con_conflictos"
        : isReviewed
          ? "revisada"
          : isCritical
            ? "critica"
            : "sin_revisar";

  const conflictWord = conflictCount === 1 ? "conflicto" : "conflictos";

  return (
    <div className="flex flex-1 items-center justify-between gap-4 text-left">
      <div className="flex items-center gap-2">
        <Icon data-icon={Icon.displayName ?? Icon.name} className="h-5 w-5 text-gray-700" />
        <span className="font-semibold text-gray-900">{name}</span>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-600">
          {`${extractedCount} extraídos • ${notFoundCount} no encontrados • ${conflictCount} ${conflictWord}`}
        </span>
        {conflictCount > 0 ? <span className="text-xs font-semibold text-error">{conflictCount} conflictos sin resolver</span> : null}
        <FieldStateBadge state={state} />
      </div>
    </div>
  );
}
