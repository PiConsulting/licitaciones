import { Plus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/Button";
import { EventCard, ConfirmedEvent } from "../../components/timeline/EventCard";
import { PendingEventCard } from "../../components/timeline/PendingEventCard";
import { TimelineEmptyState } from "../../components/timeline/TimelineEmptyState";
import { TimelineStats } from "../../components/timeline/TimelineStats";
import { getTimelineEvents, getTimelineDeadlines } from "../../api/timeline";

interface TimelineTabProps {
  analysisId: string;
}

export function TimelineTab({ analysisId }: TimelineTabProps) {
  const { data: events, isLoading: eventsLoading, isError: eventsError } = useQuery({
    queryKey: ["timeline", analysisId],
    queryFn: () => getTimelineEvents(analysisId),
  });

  const { data: deadlines, isLoading: deadlinesLoading } = useQuery({
    queryKey: ["timeline-deadlines", analysisId],
    queryFn: () => getTimelineDeadlines(analysisId),
  });

  const isLoading = eventsLoading || deadlinesLoading;
  const isError = eventsError;

  const handleAddEvent = () => {
    // Story 19-1: Modal para agregar evento
    // TODO: Implementar modal
  };

  const handleAddDate = (eventId: string) => {
    // Story 19-2: Modal agregar fecha
    // TODO: Implementar modal para eventId
  };

  // Helper: obtener deadline y trigger event para un evento dado
  // Nota: Si un evento tiene múltiples deadlines, solo retorna el primero encontrado
  const getEventDependency = (eventId: string) => {
    if (!deadlines) return null;
    
    const deadline = deadlines.find((d) => d.target_event_id === eventId && !d.deleted);
    if (!deadline) return null;

    const triggerEvent = events?.find((e) => e.event_id === deadline.trigger_event_id);
    return { deadline, triggerEvent };
  };

  // Helper: verificar si un evento es trigger de algún deadline
  const hasEventDependents = (eventId: string): boolean => {
    if (!deadlines) return false;
    return deadlines.some(
      (d) => d.trigger_event_id === eventId && !d.deleted
    );
  };

  // Filtrar eventos con fecha y ordenar cronológicamente
  const eventsWithDate =
    events
      ?.filter((e) => e.event_date !== null && !e.deleted)
      .sort((a, b) => new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime()) || [];

  // Filtrar eventos sin fecha (pendientes)
  const pendingEvents = events?.filter((e) => e.event_date === null && !e.deleted) || [];

  const hasEvents = eventsWithDate.length > 0 || pendingEvents.length > 0;

  return (
    <div className="timeline-tab">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Timeline</h2>
          <p className="text-sm text-gray-600 mt-1">Eventos y plazos del proceso de licitación</p>
        </div>
        <Button variant="primary" size="sm" onClick={handleAddEvent}>
          <Plus className="w-4 h-4 mr-1.5" />
          Agregar evento
        </Button>
      </div>

      {/* Timeline Stats - solo si hay eventos */}
      {hasEvents && (
        <TimelineStats
          totalEvents={eventsWithDate.length + pendingEvents.length}
          confirmedEvents={eventsWithDate.length}
          pendingEvents={pendingEvents.length}
        />
      )}

      {/* Content Area */}
      {isLoading ? (
        <div className="min-h-[200px] flex items-center justify-center">
          <p className="text-sm text-gray-500">Cargando eventos...</p>
        </div>
      ) : isError ? (
        <div className="min-h-[200px] flex items-center justify-center">
          <p className="text-sm text-error">Error al cargar eventos del timeline</p>
        </div>
      ) : !hasEvents ? (
        <TimelineEmptyState onAddEvent={handleAddEvent} />
      ) : (
        <div className="space-y-8">
          {/* Eventos Confirmados */}
          {eventsWithDate.length > 0 ? (
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-600">
                Eventos Confirmados
              </h3>
              <div className="space-y-3">
                {eventsWithDate.map((event) => {
                  const dependency = getEventDependency(event.event_id);
                  // Type assertion segura: eventsWithDate filtra event_date !== null
                  const confirmedEvent = event as ConfirmedEvent;
                  return (
                    <EventCard
                      key={event.event_id}
                      event={confirmedEvent}
                      deadline={dependency?.deadline}
                      triggerEvent={dependency?.triggerEvent}
                      onClick={() => {
                        /* Story 20-1: Modal detalle */
                      }}
                    />
                  );
                })}
              </div>
            </section>
          ) : null}

          {/* Eventos Pendientes */}
          {pendingEvents.length > 0 ? (
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-600">
                Eventos Pendientes
              </h3>
              <div className="space-y-3">
                {pendingEvents.map((event) => (
                  <PendingEventCard
                    key={event.event_id}
                    event={event}
                    hasDependents={hasEventDependents(event.event_id)}
                    onAddDate={() => handleAddDate(event.event_id)}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
