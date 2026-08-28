import { Badge, BadgeTone } from "../Badge";
import { Event, DateSource, Deadline } from "../../types/timeline";
import { DependencyIndicator } from "./DependencyIndicator";
import { ErrorIndicator } from "./ErrorIndicator";
import { formatEventDate } from "../../utils/dates";

// Tipo refinado: evento con fecha confirmada (no null)
export type ConfirmedEvent = Event & { event_date: string };

interface EventCardProps {
  event: ConfirmedEvent;
  deadline?: Deadline;
  triggerEvent?: Event;
  onClick?: () => void;
}

const DATE_SOURCE_CONFIG: Record<DateSource, { label: string; tone: BadgeTone }> = {
  detected: { label: "Detectada", tone: "info" },
  user_input: { label: "Ingresada", tone: "success" },
  calculated: { label: "Calculada", tone: "warning" },
  pending: { label: "Pendiente", tone: "neutral" },
};

export function EventCard({ event, deadline, triggerEvent, onClick }: EventCardProps) {
  const config = DATE_SOURCE_CONFIG[event.date_source];
  const hasCalculationError =
    deadline?.calculation_status === "error" && deadline.calculation_error;

  return (
    <div
      onClick={onClick}
      className="event-card rounded-lg border border-gray-200 p-4 transition-colors hover:bg-gray-50 cursor-pointer"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-medium text-gray-900">{event.name}</h3>
          <p className="mt-1 text-sm text-gray-600">{formatEventDate(event.event_date)}</p>
        </div>
        <Badge tone={config.tone}>{config.label}</Badge>
      </div>

      {/* Mostrar error de cálculo si existe */}
      {hasCalculationError && (
        <div className="mt-3">
          <ErrorIndicator error={deadline.calculation_error!} />
        </div>
      )}

      {/* Dependency indicator solo si no hay error */}
      {deadline && !hasCalculationError && (
        <DependencyIndicator deadline={deadline} triggerEvent={triggerEvent} />
      )}
    </div>
  );
}
