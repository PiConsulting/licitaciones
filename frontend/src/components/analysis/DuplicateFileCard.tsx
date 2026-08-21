import type { DuplicateAction, DuplicateWarning } from "../../types/analysis";

interface DuplicateFileCardProps {
  duplicate: DuplicateWarning;
  action: DuplicateAction;
  onActionChange: (action: DuplicateAction) => void;
}

const ACTION_OPTIONS: Array<{ value: DuplicateAction; label: string }> = [
  { value: "view_existing", label: "Ver análisis existente" },
  { value: "analyze_again", label: "Analizar de nuevo" },
  { value: "cancel", label: "Cancelar" },
];

export function DuplicateFileCard({ duplicate, action, onActionChange }: DuplicateFileCardProps) {
  const formattedDate = new Date(duplicate.created_at).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

  return (
    <article className="rounded-md border border-amber-200 bg-amber-50 p-4">
      <h3 className="text-sm font-semibold text-gray-900">{duplicate.filename}</h3>
      <p className="mt-1 text-xs text-amber-900">
        Ya fue analizado el {formattedDate} por {duplicate.created_by}
      </p>
      <p className="mt-2 text-xs text-gray-700">¿Qué querés hacer con este archivo?</p>
      <select
        className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
        value={action}
        onChange={(event) => onActionChange(event.target.value as DuplicateAction)}
      >
        {ACTION_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </article>
  );
}
