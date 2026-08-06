import { AlertTriangle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "../../components/Badge";
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
  notApplicableCount: number;
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
  notApplicableCount,
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

      <div className="flex flex-wrap items-center gap-1.5">
        {extractedCount > 0 ? <Badge tone="success">{`${extractedCount} extraídos`}</Badge> : null}
        {notFoundCount > 0 ? <Badge tone="warning">{`${notFoundCount} no encontrados`}</Badge> : null}
        {conflictCount > 0 ? (
          <Badge tone="error" icon={AlertTriangle}>{`${conflictCount} ${conflictWord}`}</Badge>
        ) : null}
        {notApplicableCount > 0 ? <Badge tone="info">{`${notApplicableCount} no aplica`}</Badge> : null}
        <FieldStateBadge state={state} />
      </div>
    </div>
  );
}
