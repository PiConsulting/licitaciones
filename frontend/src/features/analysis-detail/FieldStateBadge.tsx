import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";

import { Badge, type BadgeTone } from "../../components/Badge";

type CategoryVisualState =
  | "sin_revisar"
  | "revisada"
  | "critica"
  | "error"
  | "con_conflictos"
  | "no_aplica"
  | "no_analizada";

const STATE_BADGES: Record<
  CategoryVisualState,
  {
    text: string;
    tone: BadgeTone;
    icon: typeof CheckCircle | typeof XCircle | typeof AlertTriangle | null;
  }
> = {
  sin_revisar: {
    text: "SIN REVISAR",
    tone: "neutral",
    icon: null,
  },
  revisada: {
    text: "REVISADA",
    tone: "success",
    icon: CheckCircle,
  },
  critica: {
    text: "CRÍTICA",
    tone: "highlight",
    icon: null,
  },
  error: {
    text: "ERROR",
    tone: "error",
    icon: XCircle,
  },
  con_conflictos: {
    text: "CONFLICTOS",
    tone: "error",
    icon: AlertTriangle,
  },
  no_aplica: {
    text: "NO APLICA",
    tone: "info",
    icon: null,
  },
  // CTX-03: la categoría existe en el contrato pero ningún extractor la
  // completa. Decir "no encontrado" acá es afirmar algo sobre el pliego que el
  // sistema nunca verificó.
  no_analizada: {
    text: "NO ANALIZADA",
    tone: "neutral",
    icon: null,
  },
};

interface FieldStateBadgeProps {
  state: CategoryVisualState;
}

export function FieldStateBadge({ state }: FieldStateBadgeProps) {
  const config = STATE_BADGES[state];

  return (
    <Badge tone={config.tone} icon={config.icon ?? undefined}>
      {state === "critica" ? "⭐ " : ""}
      {state === "revisada" ? "✓ " : ""}
      {config.text}
    </Badge>
  );
}
