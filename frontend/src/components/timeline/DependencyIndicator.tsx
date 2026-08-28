import { ArrowRight } from "lucide-react";
import type { Deadline, Event } from "../../types/timeline";

interface DependencyIndicatorProps {
  deadline: Deadline;
  triggerEvent?: Event;
}

const DAY_TYPE_LABEL: Record<string, string> = {
  corridos: "corridos",
  hábiles: "hábiles",
  no_especificado: "(tipo no especificado)",
};

export function DependencyIndicator({ deadline, triggerEvent }: DependencyIndicatorProps) {
  const dayTypeLabel = DAY_TYPE_LABEL[deadline.day_type] || deadline.day_type;

  if (!triggerEvent || triggerEvent.event_date === null) {
    return (
      <div className="mt-2 flex items-center gap-2 text-sm text-gray-500">
        <ArrowRight className="h-4 w-4" />
        <span>Pendiente de fecha de {triggerEvent?.name?.trim() || "evento anterior"}</span>
      </div>
    );
  }

  return (
    <div className="mt-2 flex items-center gap-2 text-sm text-gray-600">
      <ArrowRight className="h-4 w-4" />
      <span>
        {deadline.duration} días {dayTypeLabel} desde {triggerEvent.name?.trim() || "evento"}
      </span>
    </div>
  );
}
