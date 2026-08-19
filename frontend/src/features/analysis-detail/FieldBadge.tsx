import { Badge, type BadgeTone } from "../../components/Badge";
import type { ConfidenceLevel } from "./types";

const CONFIDENCE_TONES: Record<ConfidenceLevel, { text: string; tone: BadgeTone; tooltip: string }> = {
  high: { text: "Alta", tone: "success", tooltip: "Nivel de confianza: alta" },
  medium: { text: "Media", tone: "warning", tooltip: "Nivel de confianza: media" },
  low: { text: "Baja", tone: "critical", tooltip: "Nivel de confianza: baja" },
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
      className="normal-case px-1.5 py-0.5 text-[10px] font-medium opacity-90"
    >
      {config.text}
    </Badge>
  );
}
