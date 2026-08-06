interface StatusFilterProps {
  value: string;
  onChange: (value: string) => void;
}

const STATUS_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "queued", label: "En cola" },
  { value: "analyzing", label: "Analizando" },
  { value: "analyzed", label: "Analizado" },
  { value: "validated", label: "Validado" },
  { value: "error", label: "Error" },
  { value: "cancelled", label: "Cancelado" },
];

export function StatusFilter({ value, onChange }: StatusFilterProps) {
  return (
    <label className="flex min-w-40 flex-col gap-1">
      <span className="text-sm font-medium text-gray-700">Estado</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-md border border-gray-200 px-3 py-2 text-sm focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        {STATUS_OPTIONS.map((option) => (
          <option key={option.value || "all"} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
