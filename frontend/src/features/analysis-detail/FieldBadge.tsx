import type { ConfidenceLevel } from "./types";

const CONFIDENCE_BADGES: Record<ConfidenceLevel, { text: string; className: string }> = {
  high: {
    text: "ALTA",
    className: "bg-success-light text-success border-success",
  },
  medium: {
    text: "MEDIA",
    className: "bg-warning-light text-warning border-warning",
  },
  low: {
    text: "BAJA",
    className: "bg-critical-light text-critical border-critical",
  },
};

interface FieldBadgeProps {
  level: ConfidenceLevel;
}

export function FieldBadge({ level }: FieldBadgeProps) {
  const config = CONFIDENCE_BADGES[level];

  return (
    <span className={`rounded px-2 py-1 text-xs font-bold uppercase border ${config.className}`}>
      {config.text}
    </span>
  );
}
