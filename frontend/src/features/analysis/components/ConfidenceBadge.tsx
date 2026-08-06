interface ConfidenceBadgeProps {
  confidence?: number | null;
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  if (confidence === null || confidence === undefined) {
    return <span className="inline-flex rounded bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-600">N/A</span>;
  }

  const value = Math.round(confidence * 100);
  let className = "bg-error-light text-error";

  if (value >= 80) {
    className = "bg-success-light text-success";
  } else if (value >= 60) {
    className = "bg-warning-light text-warning";
  }

  return <span className={`inline-flex rounded px-2 py-1 text-xs font-semibold ${className}`}>{value}%</span>;
}
