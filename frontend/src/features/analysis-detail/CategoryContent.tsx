import { needsAction } from "../../utils/fieldSeverity";
import type { CategoryId, Citation, FieldItem, SourceReference } from "./types";
import { FieldCard } from "./FieldCard";
import { FieldRow } from "./FieldRow";

interface CategoryContentProps {
  summary: string;
  sourceReferences: SourceReference[];
  fields: FieldItem[];
  categoryId: CategoryId;
  onViewSource?: (payload: { citation: Citation; citations: Citation[] }) => void;
}

export function CategoryContent({ summary, sourceReferences, fields, categoryId, onViewSource }: CategoryContentProps) {
  const representativeSource = sourceReferences[0];
  const actionableFields = fields.filter(needsAction);
  const compactFields = fields.filter((field) => !needsAction(field));

  return (
    <div id={`category-content-${categoryId}`} className="space-y-2">
      <div className="rounded-md bg-gray-50 p-2">
        <p className="text-xs text-gray-900">{summary || "Sin resumen disponible."}</p>
        {representativeSource ? (
          <p className="mt-2 text-xs text-gray-600">
            {`Fuente: ${representativeSource.document_id || "Documento"} (pág. ${representativeSource.page})`}
          </p>
        ) : null}
      </div>

      {fields.length === 0 ? (
        <p className="rounded-md border border-gray-200 bg-white p-3 text-sm text-gray-600">
          No hay campos disponibles en esta categoría.
        </p>
      ) : null}

      {actionableFields.map((field) => (
        <FieldCard key={field.field_name} field={field} onViewSource={onViewSource} />
      ))}

      {compactFields.length > 0 ? (
        <ul className="divide-y divide-gray-100 rounded-md border border-gray-200 bg-white">
          {compactFields.map((field) => (
            <FieldRow key={field.field_name} field={field} onViewSource={onViewSource} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
