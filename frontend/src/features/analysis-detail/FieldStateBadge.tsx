import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";

type CategoryVisualState = "sin_revisar" | "revisada" | "critica" | "error" | "con_conflictos";

const STATE_BADGES: Record<
  CategoryVisualState,
  {
    text: string;
    className: string;
    icon: typeof CheckCircle | typeof XCircle | typeof AlertTriangle | null;
  }
> = {
  sin_revisar: {
    text: "SIN REVISAR",
    className: "bg-gray-100 text-gray-600",
    icon: null,
  },
  revisada: {
    text: "REVISADA",
    className: "bg-success-light text-success",
    icon: CheckCircle,
  },
  critica: {
    text: "CRÍTICA",
    className: "bg-critical-light text-critical",
    icon: null,
  },
  error: {
    text: "ERROR",
    className: "bg-error-light text-error",
    icon: XCircle,
  },
  con_conflictos: {
    text: "CONFLICTOS",
    className: "bg-error-light text-error",
    icon: AlertTriangle,
  },
};

interface FieldStateBadgeProps {
  state: CategoryVisualState;
}

export function FieldStateBadge({ state }: FieldStateBadgeProps) {
  const config = STATE_BADGES[state];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold uppercase ${config.className}`}>
      {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
      {state === "critica" ? "⭐ " : ""}
      {state === "revisada" ? "✓ " : ""}
      {config.text}
    </span>
  );
}
