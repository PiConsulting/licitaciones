import { Badge, type BadgeTone } from "../../components/Badge";
import type { ConfidenceLevel } from "./types";

const CONFIDENCE_TONES: Record<ConfidenceLevel, { text: string; tone: BadgeTone; borderClass: string }> = {
  high: { text: "ALTA", tone: "success", borderClass: "border-success" },
  medium: { text: "MEDIA", tone: "warning", borderClass: "border-warning" },
  low: { text: "BAJA", tone: "critical", borderClass: "border-critical" },
};

interface FieldBadgeProps {
  level: ConfidenceLevel;
}

export function FieldBadge({ level }: FieldBadgeProps) {
  const config = CONFIDENCE_TONES[level];

  return (
    <Badge tone={config.tone} className={`border font-bold ${config.borderClass}`}>
      {config.text}
    </Badge>
  );
}
