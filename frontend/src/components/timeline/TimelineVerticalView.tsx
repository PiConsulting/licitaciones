import { useState } from "react";
import { HelpCircle } from "lucide-react";
import { Badge } from "../Badge";
import { ConfirmedEvent } from "./EventCard";
import { EventDetailModal } from "./EventDetailModal";
import { DeadlineResponse, DateSource } from "../../types/timeline";
import { formatEventDate } from "../../utils/dates";
import { cn } from "../../utils/cn";

interface TimelineVerticalViewProps {
  /** Eventos con fecha, en orden estrictamente cronológico ascendente (a
   * diferencia de la lista, acá NO se prioriza a los inferidos primero --
   * en una línea de tiempo real el orden tiene que ser por fecha, si no
   * "HOY" queda en cualquier lado). */
  events: ConfirmedEvent[];
  getDependentDeadlines: (eventId: string) => DeadlineResponse[];
  getDependentEventNames: (eventId: string) => string[];
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DATE_SOURCE_DOT: Record<DateSource, string> = {
  detected: "bg-blue-500",
  user_input: "bg-green-600",
  calculated: "bg-amber-500",
  pending: "bg-gray-400",
};

export function getTodayIso(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

type Row = { kind: "today"; iso: string } | { kind: "event"; event: ConfirmedEvent };

/**
 * Vista alternativa del Timeline (2026-09-01): una línea vertical cronológica
 * con un punto por evento y un marcador de "HOY" insertado en la posición
 * que le corresponde según la fecha actual -- para ver de un vistazo qué ya
 * pasó y qué falta, en vez de leer una lista de cards.
 *
 * Es de solo lectura: un click en un evento abre el mismo EventDetailModal
 * que usa la vista de lista, para no duplicar edición/borrado/ocultar acá.
 */
export function TimelineVerticalView({
  events,
  getDependentDeadlines,
  getDependentEventNames,
  onViewSource,
}: TimelineVerticalViewProps) {
  const [selectedEvent, setSelectedEvent] = useState<ConfirmedEvent | null>(null);

  const todayIso = getTodayIso();

  const rows: Row[] = [];
  let todayInserted = false;
  for (const event of events) {
    if (!todayInserted && event.event_date >= todayIso) {
      rows.push({ kind: "today", iso: todayIso });
      todayInserted = true;
    }
    rows.push({ kind: "event", event });
  }
  if (!todayInserted) {
    rows.push({ kind: "today", iso: todayIso });
  }

  if (events.length === 0) {
    return null;
  }

  return (
    <div className="relative pl-7">
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-gray-200" aria-hidden="true" />
      <ol className="space-y-4">
        {rows.map((row) => {
          if (row.kind === "today") {
            return (
              <li key="today" className="relative flex items-center">
                <span className="absolute -left-7 flex h-[18px] w-[18px] items-center justify-center">
                  <span className="h-3 w-3 rounded-full bg-primary ring-4 ring-primary-light" />
                </span>
                <div className="rounded-full bg-primary-light px-3 py-1 text-xs font-semibold text-primary">
                  HOY -- {formatEventDate(row.iso)}
                </div>
              </li>
            );
          }

          const event = row.event;
          const isInferred = event.source_reference?.mencion_propia === false;
          const dependentNames = getDependentEventNames(event.event_id);
          const dotClass = DATE_SOURCE_DOT[event.date_source];

          return (
            <li key={event.event_id} className="relative">
              <button
                type="button"
                onClick={() => setSelectedEvent(event)}
                className={cn(
                  "group flex w-full items-start gap-3 rounded-md py-1 pr-2 text-left transition-colors hover:bg-gray-50",
                  event.hidden && "opacity-50",
                )}
              >
                <span className="absolute -left-7 mt-1 flex h-[18px] w-[18px] items-center justify-center">
                  <span className={cn("h-2.5 w-2.5 rounded-full", dotClass)} />
                </span>
                <span className="mt-0.5 shrink-0 text-xs font-medium text-gray-500">
                  {formatEventDate(event.event_date)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-1.5">
                    <span className="truncate text-sm font-medium text-gray-900">{event.name}</span>
                    {event.hidden ? (
                      <Badge tone="neutral" className="px-1.5 py-0.5 text-[10px]">
                        Oculto
                      </Badge>
                    ) : null}
                    {isInferred ? (
                      <span
                        title="El pliego no menciona este evento por sí mismo -- se creó porque otro evento depende de su fecha para calcularse."
                        aria-label="Evento inferido, sin mención propia en el pliego"
                        className="inline-flex shrink-0 items-center text-gray-400"
                      >
                        <HelpCircle className="h-3.5 w-3.5" />
                      </span>
                    ) : null}
                  </div>
                  {dependentNames.length > 0 ? (
                    <p className="truncate text-xs text-gray-500">
                      Usado por: {dependentNames.join(", ")}
                    </p>
                  ) : null}
                </div>
              </button>
            </li>
          );
        })}
      </ol>

      {selectedEvent && (
        <EventDetailModal
          event={selectedEvent}
          deadlines={getDependentDeadlines(selectedEvent.event_id)}
          open={true}
          onClose={() => setSelectedEvent(null)}
          onViewSource={onViewSource}
        />
      )}
    </div>
  );
}
