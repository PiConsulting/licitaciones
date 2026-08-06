import { ChevronRight, Eye } from "lucide-react";
import { useState } from "react";

import { cn } from "../../utils/cn";
import { getConfidenceLevel } from "../../utils/confidence";
import { ActionButton } from "./ActionButton";
import { Badge } from "../../components/Badge";
import { FieldBadge } from "./FieldBadge";
import type { FieldItem } from "./types";

interface FieldRowProps {
  field: FieldItem;
  onViewSource?: (payload: { citation: FieldItem["citations"][number]; citations: FieldItem["citations"] }) => void;
}

export function FieldRow({ field, onViewSource }: FieldRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const primaryCitation = field.citations[0];

  const handleViewSource = () => {
    if (!primaryCitation || !onViewSource) {
      return;
    }
    onViewSource({ citation: primaryCitation, citations: field.citations });
  };

  return (
    <li data-testid="field-row" className="p-2 text-sm">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setIsExpanded((previous) => !previous)}
          aria-expanded={isExpanded}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <ChevronRight
            className={cn("h-3.5 w-3.5 flex-shrink-0 text-gray-400 transition-transform", isExpanded && "rotate-90")}
          />
          <span className="w-1/3 flex-shrink-0 truncate font-medium text-gray-900">{field.field_name}</span>
          <span className="min-w-0 flex-1 truncate text-gray-600">{field.field_value ?? "—"}</span>
        </button>
        {field.field_state === "extraido" ? (
          <FieldBadge level={getConfidenceLevel(field.confidence)} />
        ) : (
          <Badge tone="info">NO APLICA</Badge>
        )}
        {primaryCitation ? <ActionButton text="Ver fuente" icon={Eye} variant="ghost" onClick={handleViewSource} /> : null}
      </div>

      {isExpanded ? (
        <div className="mt-1.5 space-y-1.5 pl-5">
          <p className="text-sm text-gray-700">{field.field_value ?? "Sin valor"}</p>
          {primaryCitation ? (
            <div className="rounded bg-gray-50 p-2 text-xs text-gray-600">
              <p className="italic">"{primaryCitation.text}"</p>
              <p className="mt-1">{`${primaryCitation.document_name} (pág. ${primaryCitation.page})`}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
