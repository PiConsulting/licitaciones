import { Plus, Eye, EyeOff, List, Clock, ChevronDown, ChevronUp } from "lucide-react";
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
  const [showHidden, setShowHidden] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [pendingExpanded, setPendingExpanded] = useState(true);

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

  const getDependentEventNames = (eventId: string): string[] =>
    getDependentDeadlines(eventId)
      .map((d) => events?.find((e) => e.event_id === d.target_event_id)?.name?.trim())
      .filter((name): name is string => Boolean(name));

  const isInferred = (e: EventResponse): boolean => e.source_reference?.mencion_propia === false;
  const byInferredFirst = (a: EventResponse, b: EventResponse) =>
    (isInferred(a) ? 0 : 1) - (isInferred(b) ? 0 : 1);

  const activeEvents = events?.filter((e) => !e.deleted && !e.hidden) || [];
  const hiddenEvents = events?.filter((e) => !e.deleted && e.hidden) || [];

  const displayEvents = showHidden ? [...activeEvents, ...hiddenEvents] : activeEvents;

  const eventsWithDate = displayEvents
    .filter((e) => e.event_date !== null)
    .sort((a, b) => {
      const inferredDiff = byInferredFirst(a, b);
      if (inferredDiff !== 0) return inferredDiff;
      return new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime();
    });

  const chronologicalEventsWithDate = [...eventsWithDate].sort(
    (a, b) => new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime(),
  );

  const pendingEvents = displayEvents.filter((e) => e.event_date === null);

  const statsWithDateCount = activeEvents.filter((e) => e.event_date !== null).length;
  const statsPendingCount = activeEvents.filter((e) => e.event_date === null).length;

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

  const hasAnyEvents = activeEvents.length > 0 || hiddenEvents.length > 0;
  const hasVisibleEvents = eventsWithDate.length > 0 || pendingEvents.length > 0;
  const today = new Date();
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const completedEventsCount = activeEvents.filter((e) => e.event_date !== null && e.event_date < todayIso).length;
  const nextUpcomingEvent = [...activeEvents]
    .filter((e) => e.event_date !== null && e.event_date >= todayIso)
    .sort((a, b) => new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime())[0];

  return (
    <div className="timeline-tab">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-center gap-2.5">
          {activeEvents.length > 0 ? (
            <nav
              className="inline-flex gap-1 rounded-full border border-[rgba(0,60,107,.12)] bg-white p-1"
              aria-label="Modo de vista del Timeline"
            >
              <button
                type="button"
                onClick={() => setViewMode("list")}
                aria-pressed={viewMode === "list"}
                className={cn(
                  "inline-flex h-8 items-center gap-[7px] rounded-full px-3.5 text-[12.5px] font-semibold transition-colors",
                  viewMode === "list" ? "bg-[#003C6B] text-white" : "bg-transparent text-[#003C6B]",
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
                  "inline-flex h-8 items-center gap-[7px] rounded-full px-3.5 text-[12.5px] font-semibold transition-colors",
                  viewMode === "timeline" ? "bg-[#003C6B] text-white" : "bg-transparent text-[#003C6B]",
                )}
              >
                <Clock className="h-3.5 w-3.5" />
                Línea de tiempo
              </button>
            </nav>
          ) : null}
          {hiddenEvents.length > 0 ? (
            <button
              type="button"
              onClick={() => setShowHidden((prev) => !prev)}
              className="inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 text-xs font-semibold text-[rgba(0,60,107,.68)] hover:border-[#0099DB] hover:text-[#003C6B]"
            >
              {showHidden ? <EyeOff className="h-[13px] w-[13px]" /> : <Eye className="h-[13px] w-[13px]" />}
              {showHidden ? "Ocultar ocultos" : `Mostrar ocultos (${hiddenEvents.length})`}
            </button>
          ) : null}
        </div>
        <button
          type="button"
          onClick={handleAddEvent}
          className="inline-flex h-9 items-center gap-2 whitespace-nowrap rounded-full border-0 bg-[#003C6B] px-[18px] text-[13px] font-semibold text-white hover:bg-[#0099DB]"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          Agregar evento
        </button>
      </div>

      {activeEvents.length > 0 ? (
        <TimelineStats
          totalEvents={activeEvents.length}
          confirmedEvents={statsWithDateCount}
          pendingEvents={statsPendingCount}
          completedEvents={completedEventsCount}
          nextUpcomingEvent={nextUpcomingEvent ? { name: nextUpcomingEvent.name, date: nextUpcomingEvent.event_date! } : null}
        />
      ) : null}

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
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">
                  Eventos Confirmados
                </h3>
                <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[rgba(0,60,107,.08)] px-1.5 text-[11px] font-bold text-[rgba(0,60,107,.68)]">
                  {eventsWithDate.length}
                </span>
              </div>
              <div className="space-y-2.5">
                {eventsWithDate.map((event) => {
                  const dependency = getEventDependency(event.event_id);
                  const dependentDeadlines = getDependentDeadlines(event.event_id);
                  const confirmedEvent = event as ConfirmedEvent;
                  const isPast = event.event_date !== null && event.event_date < todayIso;
                  const isNext = nextUpcomingEvent?.event_id === event.event_id;
                  return (
                    <EventCard
                      key={event.event_id}
                      analysisId={analysisId}
                      event={confirmedEvent}
                      deadline={dependency?.deadline}
                      triggerEvent={dependency?.triggerEvent}
                      dependentDeadlines={dependentDeadlines}
                      dependentEventNames={getDependentEventNames(event.event_id)}
                      isPast={isPast}
                      isNext={isNext}
                      onViewSource={onViewSource}
                    />
                  );
                })}
              </div>
            </section>
          ) : null}

          {otherPendingEvents.length > 0 ? (
            <section>
              <button
                type="button"
                onClick={() => setPendingExpanded((prev) => !prev)}
                aria-expanded={pendingExpanded}
                className="mb-3 flex w-full items-center gap-2 border-0 bg-transparent p-0"
              >
                <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">
                  Eventos Pendientes
                </h3>
                <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[rgba(0,60,107,.08)] px-1.5 text-[11px] font-bold text-[rgba(0,60,107,.68)]">
                  {otherPendingEvents.length}
                </span>
                {pendingExpanded ? (
                  <ChevronUp className="h-3.5 w-3.5 text-[rgba(0,60,107,.55)]" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 text-[rgba(0,60,107,.55)]" />
                )}
              </button>
              {pendingExpanded ? (
                <div className="space-y-2.5">
                  {otherPendingEvents.map((event) => {
                    const dependency = getEventDependency(event.event_id);
                    return (
                      <PendingEventCard
                        key={event.event_id}
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
              ) : null}
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
