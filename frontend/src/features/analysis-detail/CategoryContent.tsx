import type { CategoryId, FieldItem, SourceReference } from "./types";
import { FieldCard } from "./FieldCard";

interface CategoryContentProps {
  summary: string;
  sourceReferences: SourceReference[];
  fields: FieldItem[];
  categoryId: CategoryId;
}

export function CategoryContent({ summary, sourceReferences, fields, categoryId }: CategoryContentProps) {
  const representativeSource = sourceReferences[0];

  return (
    <div id={`category-content-${categoryId}`} className="space-y-3">
      <div className="rounded-md bg-gray-50 p-3">
        <p className="text-sm text-gray-900">{summary || "Sin resumen disponible."}</p>
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

      {fields.map((field) => (
        <FieldCard key={field.field_name} field={field} />
      ))}
    </div>
  );
}
