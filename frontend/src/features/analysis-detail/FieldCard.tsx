import { AlertTriangle, Edit, Eye, Plus, XCircle } from "lucide-react";

import { getConfidenceLevel } from "../../utils/confidence";
import { cn } from "../../utils/cn";
import { ActionButton } from "./ActionButton";
import { FieldBadge } from "./FieldBadge";
import type { FieldItem } from "./types";

interface FieldCardProps {
  field: FieldItem;
}

export function FieldCard({ field }: FieldCardProps) {
  const confidenceLevel = getConfidenceLevel(field.confidence);

  const cardClass = cn(
    "mb-3 rounded-md border p-4",
    field.field_state === "en_conflicto" && "border-l-4 border-l-error bg-error-light",
    field.field_state === "no_encontrado" && "border-l-4 border-l-warning bg-warning-light",
    field.field_state !== "en_conflicto" && field.field_state !== "no_encontrado" && "border-gray-200 bg-white",
  );

  const primaryCitation = field.citations[0];

  return (
    <div data-testid="field-card" className={cardClass}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-gray-900">{field.field_name}</h4>
        {field.field_state === "extraido" ? <FieldBadge level={confidenceLevel} /> : null}
      </div>

      {field.field_state === "extraido" ? (
        <p className="mb-2 text-sm text-gray-900">{field.field_value ?? "Sin valor"}</p>
      ) : null}

      {field.field_state === "no_encontrado" ? (
        <div className="mb-2 flex items-center gap-2 text-warning">
          <AlertTriangle className="h-4 w-4" />
          <p className="text-sm font-medium">No se encontró este dato</p>
        </div>
      ) : null}

      {field.field_state === "en_conflicto" ? (
        <div className="mb-2 space-y-2">
          <div className="flex items-center gap-2 text-error">
            <XCircle className="h-4 w-4" />
            <p className="text-sm font-semibold">Conflicto entre documentos</p>
          </div>
          {field.citations.map((citation, index) => (
            <div key={`${citation.document_id}-${index}`} className="rounded border border-error/30 bg-white p-2">
              <p className="text-sm text-gray-900">{citation.value ?? citation.text}</p>
              <p className="text-xs text-gray-600">{`${citation.document_name} (pág. ${citation.page})`}</p>
            </div>
          ))}
        </div>
      ) : null}

      {primaryCitation ? (
        <div className="mb-2 rounded bg-gray-50 p-2 text-xs text-gray-600">
          <p className="italic">"{primaryCitation.text.slice(0, 150)}{primaryCitation.text.length > 150 ? "..." : ""}"</p>
          <p>{`${primaryCitation.document_name} (pág. ${primaryCitation.page})`}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {field.field_state === "en_conflicto" ? (
          <ActionButton text="Resolver conflicto" icon={AlertTriangle} variant="danger" />
        ) : null}

        {field.field_state === "no_encontrado" ? (
          <ActionButton text="Agregar manualmente" icon={Plus} variant="warning" />
        ) : null}

        {field.field_state === "extraido" && confidenceLevel !== "high" ? (
          <>
            <ActionButton text="Corregir" icon={Edit} variant="warning" />
            <ActionButton text="Ver fuente" icon={Eye} variant="ghost" />
          </>
        ) : null}

        {field.field_state === "extraido" && confidenceLevel === "high" ? (
          <ActionButton text="Ver fuente" icon={Eye} variant="ghost" />
        ) : null}
      </div>
    </div>
  );
}
