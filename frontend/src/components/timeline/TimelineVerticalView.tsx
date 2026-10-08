import { useState } from "react";
import { Check, Eye, HelpCircle, Plus } from "lucide-react";
import { Badge } from "../Badge";
import { Button } from "../Button";
import { ConfirmedEvent } from "./EventCard";
import { EventDetailModal, EventDependent } from "./EventDetailModal";
import { DateSource, HighlightRegion } from "../../types/timeline";
import { formatEventDate } from "../../utils/dates";
import { cn } from "../../utils/cn";

interface TimelineVerticalViewProps {
  /** Eventos con fecha, en orden estrictamente cronológico ascendente (a
   * diferencia de la lista, acá NO se prioriza a los inferidos primero --
   * en una línea de tiempo real el orden tiene que ser por fecha, si no
   * "HOY" queda en cualquier lado). */
  events: ConfirmedEvent[];
  getDependentsForModal: (eventId: string) => EventDependent[];
  getDependentEventNames: (eventId: string) => string[];
  onAddEvent?: () => void;
  onViewSource?: (documentId: string, page: number, fragment?: string, highlightRegions?: HighlightRegion[]) => void;
}

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
  getDependentsForModal,
  getDependentEventNames,
  onAddEvent,
  onViewSource,
}: TimelineVerticalViewProps) {
  const [selectedEvent, setSelectedEvent] = useState<ConfirmedEvent | null>(null);

  const todayIso = getTodayIso();
  const nextUpcomingEventId = events.find((event) => event.event_date >= todayIso)?.event_id;

  const dateSourceLabel: Record<DateSource, string> = {
    detected: "Detectado en pliego",
    user_input: "Ingresado manualmente",
    calculated: "Calculado",
    pending: "Pendiente",
  };

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

  const daysUntil = (isoDate: string) => {
    const today = new Date(todayIso);
    const target = new Date(isoDate);
    const diffMs = target.getTime() - today.getTime();
    return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
  };

  return (
    <section className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-6 py-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <h3 className="font-display text-base font-semibold text-[#003C6B]">Línea de tiempo</h3>
        {onAddEvent ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8 rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 text-xs font-semibold text-[#003C6B]"
            onClick={onAddEvent}
          >
            <Plus className="mr-1 h-[13px] w-[13px]" />
            Agregar evento
          </Button>
        ) : null}
      </div>

      <ol className="m-0 list-none p-0" role="list">
        {rows.map((row) => {
          if (row.kind === "today") {
            return (
              <li key="today" className="grid grid-cols-[96px_28px_minmax(0,1fr)] gap-x-3">
                <div />
                <div className="flex flex-col items-center">
                  <span className="mt-[6px] inline-flex h-4 w-4 items-center justify-center rounded-full bg-[#0099DB] shadow-[0_0_0_5px_rgba(0,153,219,.2)]" />
                </div>
                <div className="pb-4">
                  <span className="inline-flex h-7 items-center rounded-full bg-[#0099DB] px-3 text-[11px] font-bold uppercase tracking-[0.12em] text-white">
                    HOY · {formatEventDate(row.iso)}
                  </span>
                </div>
              </li>
            );
          }

          const event = row.event;
          const isInferred = event.source_reference?.mencion_propia === false;
          const dependentNames = getDependentEventNames(event.event_id);
          const isDone = event.event_date < todayIso;
          const isNext = event.event_id === nextUpcomingEventId;
          const nextDaysLabel = isNext ? `Próximo · en ${daysUntil(event.event_date)} días` : "";
          const stateTag = isDone ? "Cumplido" : isNext ? nextDaysLabel : "Pendiente";
          const stateTagClass = isDone
            ? "bg-[rgba(127,243,222,.35)] text-[#0B6B58]"
            : isNext
              ? "bg-[#0099DB] text-white"
              : "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]";
          const cardClass = isNext ? "border-[#0099DB] bg-[#F4F9FC]" : "border-[rgba(0,60,107,.12)] bg-white";

          const dotClass = isDone
            ? "h-[22px] w-[22px] bg-[#003C6B]"
            : isNext
              ? "h-[22px] w-[22px] border-[3px] border-[#0099DB] bg-white"
              : "h-[22px] w-[22px] border-2 border-[rgba(0,60,107,.25)] bg-white";

          const lineClass = isDone ? "bg-[#003C6B]" : "bg-[rgba(0,60,107,.15)]";
          const hasLine = rows[rows.length - 1] !== row;

          return (
            <li key={event.event_id} className="grid grid-cols-[96px_28px_minmax(0,1fr)] gap-x-3">
              <div className="pt-[13px] text-right font-display text-xs font-semibold text-[#003C6B]">
                {formatEventDate(event.event_date)}
              </div>
              <div className="flex flex-col items-center self-stretch">
                <span className={`mt-3 inline-flex shrink-0 items-center justify-center rounded-full ${dotClass}`} />
                {isDone ? <Check className="absolute h-3 w-3 text-white" aria-hidden="true" /> : null}
                {hasLine ? <span className={`my-1 min-h-7 w-[2px] flex-1 rounded-full ${lineClass}`} /> : null}
              </div>
              <button
                type="button"
                onClick={() => setSelectedEvent(event)}
                className={cn(
                  `mb-4 flex w-full flex-col gap-1 rounded-xl border px-4 py-3 text-left transition-colors ${cardClass}`,
                  event.hidden && "opacity-50",
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className={cn("truncate text-sm font-semibold", isDone || isNext ? "text-[#003C6B]" : "text-[rgba(0,60,107,.68)]")}>{event.name}</span>
                  <span className={`inline-flex rounded-full px-[10px] py-[3px] text-[11px] font-bold ${stateTagClass}`}>
                    {stateTag}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs text-[rgba(0,60,107,.55)]">
                  <span>{dateSourceLabel[event.date_source]}</span>
                  {isInferred ? (
                    <span
                      title="El pliego no menciona este evento por sí mismo -- se creó porque otro evento depende de su fecha para calcularse."
                      aria-label="Evento inferido, sin mención propia en el pliego"
                      className="inline-flex shrink-0 items-center text-gray-400"
                    >
                      <HelpCircle className="h-3.5 w-3.5" />
                    </span>
                  ) : null}
                  {event.hidden ? (
                    <Badge tone="neutral" className="px-1.5 py-0.5 text-[10px]">
                      Oculto
                    </Badge>
                  ) : null}
                </div>

                {dependentNames.length > 0 ? (
                  <p className="truncate text-xs text-[rgba(0,60,107,.68)]">Usado por: {dependentNames.join(", ")}</p>
                ) : null}

                {event.source_fragment ? (
                  <p className="text-[13px] leading-[1.5] text-[rgba(0,60,107,.68)]">{event.source_fragment}</p>
                ) : null}

                <div className="mt-0.5 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold text-[rgba(0,60,107,.55)]">{dateSourceLabel[event.date_source]}</span>
                  {onViewSource && event.source_document_id && event.source_page ? (
                    <button
                      type="button"
                      onClick={(clickEvent) => {
                        clickEvent.preventDefault();
                        clickEvent.stopPropagation();
                        onViewSource(event.source_document_id!, event.source_page!, event.source_fragment, event.highlight_regions);
                      }}
                      className="inline-flex h-6 items-center gap-1 rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2 text-[11px] font-semibold text-[#0099DB] hover:border-[#0099DB]"
                      title={`Ver fuente en el pliego (pág. ${event.source_page})`}
                    >
                      <Eye className="h-3 w-3" />
                      {`pág. ${event.source_page}`}
                    </button>
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
          dependents={getDependentsForModal(selectedEvent.event_id)}
          open={true}
          onClose={() => setSelectedEvent(null)}
          onViewSource={onViewSource}
        />
      )}
    </section>
  );
}
