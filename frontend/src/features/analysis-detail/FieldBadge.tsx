import { Badge, type BadgeTone } from "../../components/Badge";
import type { ConfidenceLevel } from "./types";

const CONFIDENCE_TONES: Record<ConfidenceLevel, { text: string; tone: BadgeTone; tooltip: string; className: string }> = {
  high: {
    text: "Alta",
    tone: "success",
    tooltip: "Nivel de confianza: alta",
    className: "bg-[rgba(127,243,222,.35)] text-[#0B6B58]",
  },
  medium: {
    text: "Media",
    tone: "warning",
    tooltip: "Nivel de confianza: media",
    className: "bg-[rgba(169,102,255,.14)] text-[#6E2FC9]",
  },
  low: {
    text: "Baja",
    tone: "critical",
    tooltip: "Nivel de confianza: baja",
    className: "bg-[#FEE2E2] text-[#DC2626]",
  },
};

interface FieldBadgeProps {
  level: ConfidenceLevel;
}

export function FieldBadge({ level }: FieldBadgeProps) {
  const config = CONFIDENCE_TONES[level];

  return (
    <Badge
      tone={config.tone}
      title={config.tooltip}
      className={`normal-case px-[10px] py-1 text-[11px] font-bold opacity-100 ${config.className}`}
    >
      {config.text}
    </Badge>
  );
}
