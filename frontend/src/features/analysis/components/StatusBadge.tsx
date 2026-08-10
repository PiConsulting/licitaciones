interface StatusBadgeProps {
  status: string;
}

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-gray-100 text-gray-500",
  validated: "bg-success-light text-success",
  analyzing: "bg-warning-light text-warning",
  processing: "bg-warning-light text-warning",
  error: "bg-error-light text-error",
  queued: "bg-gray-100 text-gray-600",
  analyzed: "bg-info-light text-info",
  cancelled: "bg-gray-100 text-gray-600",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  validated: "Validado",
  analyzing: "Analizando",
  processing: "Procesando",
  error: "Error",
  queued: "En cola",
  analyzed: "Analizado",
  cancelled: "Cancelado",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  const className = STATUS_STYLES[normalized] ?? "bg-gray-100 text-gray-600";
  const label = STATUS_LABELS[normalized] ?? status;

  return <span className={`inline-flex rounded px-2 py-1 text-xs font-semibold ${className}`}>{label}</span>;
}
