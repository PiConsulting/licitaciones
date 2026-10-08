interface ConfidenceBadgeProps {
  confidence?: number | null;
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  if (confidence === null || confidence === undefined) {
    return (
      <span className="inline-flex rounded-full bg-cedi-navy-8 px-[10px] py-1 text-[11px] font-bold text-cedi-navy-68">
        Sin dato
      </span>
    );
  }

  let label = "Baja";
  let className = "bg-[#FEE2E2] text-[#DC2626]";

  if (confidence >= 0.8) {
    label = "Alta";
    className = "bg-[rgba(127,243,222,.35)] text-[#0B6B58]";
  } else if (confidence >= 0.6) {
    label = "Media";
    className = "bg-[rgba(169,102,255,.14)] text-[#6E2FC9]";
  }

  return <span className={`inline-flex rounded-full px-[10px] py-1 text-[11px] font-bold ${className}`}>{label}</span>;
}
