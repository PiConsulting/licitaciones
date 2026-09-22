import { Plus, Eye, EyeOff, List, Clock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "../../components/Button";
import { EventCard, ConfirmedEvent } from "../../components/timeline/EventCard";
import { PendingEventCard } from "../../components/timeline/PendingEventCard";
import { AnchorDatesPanel } from "../../components/timeline/AnchorDatesPanel";
import { TimelineEmptyState } from "../../components/timeline/TimelineEmptyState";
import { TimelineStats } from "../../components/timeline/TimelineStats";
import { TimelineVerticalView } from "../../components/timeline/TimelineVerticalView";
import { AddEventModal } from "../../components/timeline/AddEventModal";
import { AddDateModal } from "../../components/timeline/AddDateModal";
import { getTimelineEvents, getTimelineDeadlines } from "../../api/timeline";
import type { EventResponse } from "../../types/timeline";
import { cn } from "../../utils/cn";

type ViewMode = "list" | "timeline";

interface TimelineTabProps {
  analysisId: string;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

export function TimelineTab({ analysisId, onViewSource }: TimelineTabProps) {
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedEventForDate, setSelectedEventForDate] = useState<EventResponse | null>(null);
  // Por default los eventos ocultados a mano no se muestran ni influyen en nada; este toggle los trae de vuelta atenuados, sin perder trazabilidad.
  const [showHidden, setShowHidden] = useState(false);
  // "Lista" es el detalle de siempre; "Línea de tiempo" es una vista vertical cronológica de solo lectura, con HOY marcado (ver TimelineVerticalView).
  const [viewMode, setViewMode] = useState<ViewMode>("list");

  // Se pide siempre con include_hidden para togglear visibilidad al instante; el filtrado real pasa del lado del cliente (ver `displayEvents`).
  const { data: events, isLoading: eventsLoading, isError: eventsError } = useQuery({
    queryKey: ["timeline", analysisId],
    queryFn: () => getTimelineEvents(analysisId, { includeHidden: true }),
  });

  const { data: deadlines, isLoading: deadlinesLoading } = useQuery({
    queryKey: ["timeline-deadlines", analysisId],
    queryFn: () => getTimelineDeadlines(analysisId),
  });

  const isLoading = eventsLoading || deadlinesLoading;
  const isError = eventsError;

  const handleAddEvent = () => {
    setShowAddModal(true);
  };

  const handleAddDate = (eventId: string) => {
    const event = events?.find((e) => e.event_id === eventId);
    if (event) {
      setSelectedEventForDate(event);
    }
  };

  // Si un evento tiene múltiples deadlines, solo retorna el primero encontrado.
  const getEventDependency = (eventId: string) => {
    if (!deadlines) return null;
    
    const deadline = deadlines.find((d) => d.target_event_id === eventId && !d.deleted);
    if (!deadline) return null;

    const triggerEvent = events?.find((e) => e.event_id === deadline.trigger_event_id);
    return { deadline, triggerEvent };
  };

  const hasEventDependents = (eventId: string): boolean => {
    if (!deadlines) return false;
    return deadlines.some(
      (d) => d.trigger_event_id === eventId && !d.deleted
    );
  };

  const getDependentDeadlines = (eventId: string) => {
    if (!deadlines) return [];
    return deadlines.filter(
      (d) => d.trigger_event_id === eventId && !d.deleted
    );
  };

  // Nombres de los eventos que usan este como evento_disparador, para mostrar "Usado por: X, Y" en vez de un genérico "otros eventos dependen de esto".
  const getDependentEventNames = (eventId: string): string[] =>
    getDependentDeadlines(eventId)
      .map((d) => events?.find((e) => e.event_id === d.target_event_id)?.name?.trim())
      .filter((name): name is string => Boolean(name));

  // Evento "inferido": el pliego no lo menciona, se creó porque otro evento lo necesita como disparador (ver mencion_propia); van primero para que el usuario los verifique.
  const isInferred = (e: EventResponse): boolean => e.source_reference?.mencion_propia === false;
  const byInferredFirst = (a: EventResponse, b: EventResponse) =>
    (isInferred(a) ? 0 : 1) - (isInferred(b) ? 0 : 1);

  // Base de las estadísticas del timeline: NUNCA cuentan un evento oculto, se muestre o no en la lista (ver "Mostrar ocultos").
  const activeEvents = events?.filter((e) => !e.deleted && !e.hidden) || [];
  const hiddenEvents = events?.filter((e) => !e.deleted && e.hidden) || [];

  const displayEvents = showHidden ? [...activeEvents, ...hiddenEvents] : activeEvents;

  // Prioriza los inferidos, ordena el resto cronológicamente.
  const eventsWithDate = displayEvents
    .filter((e) => e.event_date !== null)
    .sort((a, b) => {
      const inferredDiff = byInferredFirst(a, b);
      if (inferredDiff !== 0) return inferredDiff;
      return new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime();
    });

  // Orden puramente cronológico (sin prioridad de inferidos): la línea de tiempo necesita el orden real para insertar "HOY" en el lugar correcto.
  const chronologicalEventsWithDate = [...eventsWithDate].sort(
    (a, b) => new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime(),
  );

  const pendingEvents = displayEvents.filter((e) => e.event_date === null);

  // Siempre sobre `activeEvents`: un evento oculto no debe influir en el estado general del timeline aunque el usuario lo esté mirando.
  const statsWithDateCount = activeEvents.filter((e) => e.event_date !== null).length;
  const statsPendingCount = activeEvents.filter((e) => e.event_date === null).length;

  // Eventos "ancla": pendientes de los que depende al menos un plazo; van al panel compacto (no card grande) para no repetir la misma acción dos veces.
  const anchorEvents = pendingEvents
    .filter((e) => hasEventDependents(e.event_id))
    .sort(byInferredFirst);
  const anchorEventIds = new Set(anchorEvents.map((e) => e.event_id));
  const otherPendingEvents = pendingEvents
    .filter((e) => !anchorEventIds.has(e.event_id))
    .sort(byInferredFirst);

  const dependentCountByEventId: Record<string, number> = {};
  const dependentEventNamesByEventId: Record<string, string[]> = {};
  for (const anchor of anchorEvents) {
    dependentCountByEventId[anchor.event_id] = getDependentDeadlines(anchor.event_id).length;
    dependentEventNamesByEventId[anchor.event_id] = getDependentEventNames(anchor.event_id);
  }

  // Cuenta los ocultos también: un análisis con solo eventos ocultos no está "vacío", solo hace falta prender "Mostrar ocultos".
  const hasAnyEvents = activeEvents.length > 0 || hiddenEvents.length > 0;
  const hasVisibleEvents = eventsWithDate.length > 0 || pendingEvents.length > 0;

  return (
    <div className="timeline-tab">
      <div className="mb-6">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Timeline</h2>
            <p className="text-sm text-gray-600 mt-1">Eventos y plazos del proceso de licitación</p>
          </div>
          <Button variant="primary" size="sm" className="whitespace-nowrap text-xs" onClick={handleAddEvent}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            Agregar evento
          </Button>
        </div>

        {/* Fila propia para "qué ver", separada de "Agregar evento" (la acción principal, arriba a la derecha). */}
        {(activeEvents.length > 0 || hiddenEvents.length > 0) && (
          <div className="mt-3 flex items-center gap-2">
            {activeEvents.length > 0 ? (
              <div
                className="flex items-center rounded-md border border-gray-200 p-0.5 text-xs"
                role="group"
                aria-label="Modo de vista del Timeline"
              >
                <button
                  type="button"
                  onClick={() => setViewMode("list")}
                  aria-pressed={viewMode === "list"}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 font-medium transition-colors",
                    viewMode === "list" ? "bg-primary text-primary-fg" : "text-gray-600 hover:bg-gray-50",
                  )}
                >
                  <List className="h-3.5 w-3.5" />
                  Lista
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("timeline")}
                  aria-pressed={viewMode === "timeline"}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 font-medium transition-colors",
                    viewMode === "timeline" ? "bg-primary text-primary-fg" : "text-gray-600 hover:bg-gray-50",
                  )}
                >
                  <Clock className="h-3.5 w-3.5" />
                  Línea de tiempo
                </button>
              </div>
            ) : null}
            {hiddenEvents.length > 0 ? (
              <Button
                variant="secondary"
                size="sm"
                className="whitespace-nowrap text-xs"
                onClick={() => setShowHidden((prev) => !prev)}
              >
                {showHidden ? (
                  <EyeOff className="w-3.5 h-3.5 mr-1" />
                ) : (
                  <Eye className="w-3.5 h-3.5 mr-1" />
                )}
                {showHidden ? "Ocultar ocultos" : `Mostrar ocultos (${hiddenEvents.length})`}
              </Button>
            ) : null}
          </div>
        )}
      </div>

      {activeEvents.length > 0 && (
        <TimelineStats
          totalEvents={activeEvents.length}
          confirmedEvents={statsWithDateCount}
          pendingEvents={statsPendingCount}
        />
      )}

      {isLoading ? (
        <div className="min-h-[200px] flex items-center justify-center">
          <p className="text-sm text-gray-500">Cargando eventos...</p>
        </div>
      ) : isError ? (
        <div className="min-h-[200px] flex items-center justify-center">
          <p className="text-sm text-error">Error al cargar eventos del timeline</p>
        </div>
      ) : !hasAnyEvents ? (
        <TimelineEmptyState onAddEvent={handleAddEvent} />
      ) : !hasVisibleEvents ? (
        <div className="min-h-[120px] flex flex-col items-center justify-center gap-2 text-center">
          <p className="text-sm text-gray-500">
            Todos los eventos de este análisis están ocultos por el momento.
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="whitespace-nowrap text-xs"
            onClick={() => setShowHidden(true)}
          >
            <Eye className="w-3.5 h-3.5 mr-1" />
            Mostrar ocultos ({hiddenEvents.length})
          </Button>
        </div>
      ) : viewMode === "timeline" ? (
        // La línea de tiempo muestra SOLO eventos confirmados (con fecha) -- nada de anclas por cargar ni pendientes, para no mezclar con lo que no tiene dónde ubicarse.
        eventsWithDate.length > 0 ? (
          <TimelineVerticalView
            events={chronologicalEventsWithDate as ConfirmedEvent[]}
            getDependentDeadlines={getDependentDeadlines}
            getDependentEventNames={getDependentEventNames}
            onViewSource={onViewSource}
          />
        ) : (
          <div className="min-h-[120px] flex items-center justify-center text-center">
            <p className="text-sm text-gray-500">
              Todavía no hay eventos con fecha confirmada para mostrar en la línea de tiempo.
            </p>
          </div>
        )
      ) : (
        <div className="space-y-8">
          <AnchorDatesPanel
            analysisId={analysisId}
            anchorEvents={anchorEvents}
            dependentCountByEventId={dependentCountByEventId}
            dependentEventNamesByEventId={dependentEventNamesByEventId}
            onViewSource={onViewSource}
          />

          {eventsWithDate.length > 0 ? (
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-600">
                Eventos Confirmados
              </h3>
              <div className="space-y-3">
                {eventsWithDate.map((event) => {
                  const dependency = getEventDependency(event.event_id);
                  const dependentDeadlines = getDependentDeadlines(event.event_id);
                  // Type assertion segura: eventsWithDate filtra event_date !== null
                  const confirmedEvent = event as ConfirmedEvent;
                  return (
                    <EventCard
                      key={event.event_id}
                      analysisId={analysisId}
                      event={confirmedEvent}
                      deadline={dependency?.deadline}
                      triggerEvent={dependency?.triggerEvent}
                      dependentDeadlines={dependentDeadlines}
                      dependentEventNames={getDependentEventNames(event.event_id)}
                      onViewSource={onViewSource}
                    />
                  );
                })}
              </div>
            </section>
          ) : null}

          {/* Los que ya son targets de un plazo muestran la fórmula de cálculo; los ancla no se repiten acá, ya están arriba en el panel compacto. */}
          {otherPendingEvents.length > 0 ? (
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-600">
                Eventos Pendientes
              </h3>
              <div className="space-y-2">
                {otherPendingEvents.map((event) => {
                  const dependency = getEventDependency(event.event_id);
                  return (
                    <PendingEventCard
                      key={event.event_id}
                      analysisId={analysisId}
                      event={event}
                      hasDependents={hasEventDependents(event.event_id)}
                      dependentEventNames={getDependentEventNames(event.event_id)}
                      deadline={dependency?.deadline}
                      triggerEvent={dependency?.triggerEvent}
                      onAddDate={() => handleAddDate(event.event_id)}
                      onViewSource={onViewSource}
                    />
                  );
                })}
              </div>
            </section>
          ) : null}
        </div>
      )}

      <AddEventModal
        analysisId={analysisId}
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
      />

      {selectedEventForDate && (
        <AddDateModal
          event={selectedEventForDate}
          open={true}
          onClose={() => setSelectedEventForDate(null)}
        />
      )}
    </div>
  );
}
