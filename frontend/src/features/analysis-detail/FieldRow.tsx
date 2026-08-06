import { Eye } from "lucide-react";

import { ActionButton } from "./ActionButton";
import type { FieldItem } from "./types";

interface FieldRowProps {
  field: FieldItem;
  onViewSource?: (payload: { citation: FieldItem["citations"][number]; citations: FieldItem["citations"] }) => void;
}

function buildCompactValue(field: FieldItem): string {
  if (field.field_state === "extraido") {
    return field.field_value?.trim() || "Sin valor";
  }
  if (field.field_state === "no_encontrado") {
    return "No encontrado";
  }
  if (field.field_state === "no_aplica") {
    return "No aplica";
  }
  return "En conflicto";
}

export function FieldRow({ field, onViewSource }: FieldRowProps) {
  const primaryCitation = field.citations[0];

  const handleViewSource = () => {
    if (!primaryCitation || !onViewSource) {
      return;
    }
    onViewSource({ citation: primaryCitation, citations: field.citations });
  };

  return (
    <div className="flex items-start justify-between gap-3 rounded border border-gray-200 bg-white px-3 py-2" data-testid="field-row">
      <div className="min-w-0">
        <p className="text-xs font-semibold text-gray-800">{field.field_name}</p>
        <p className="text-sm text-gray-700">{buildCompactValue(field)}</p>
      </div>
      {primaryCitation ? <ActionButton text="Ver fuente" icon={Eye} variant="ghost" onClick={handleViewSource} /> : null}
    </div>
  );
}
