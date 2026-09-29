import { useState } from "react";
import { CalendarClock, ChevronDown, ChevronUp, Eye, EyeOff, HelpCircle } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DatePicker } from "../DatePicker";
import { updateEvent, recalculateDependentDates, setEventHidden } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import type { EventResponse } from "../../types/timeline";
import { buildMarkedDates } from "./markedDates";

interface AnchorDatesPanelProps {
  analysisId: string;
  anchorEvents: EventResponse[];
  dependentCountByEventId: Record<string, number>;
  dependentEventNamesByEventId?: Record<string, string[]>;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

export function AnchorDatesPanel({
  analysisId,
  anchorEvents,
  dependentCountByEventId,
  dependentEventNamesByEventId,
  onViewSource,
}: AnchorDatesPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [isExpanded, setIsExpanded] = useState(true);
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const cachedEvents = queryClient.getQueryData<EventResponse[]>(["timeline", analysisId]);

  const saveMutation = useMutation({
    mutationFn: async ({ event, newDate }: { event: EventResponse; newDate: string }) => {
      await updateEvent(analysisId, event.event_id, {
        event_date: newDate,
        date_source: "user_input",
      });
      try {
        const stats = await recalculateDependentDates(analysisId, event.event_id);
        return { event, stats, recalcFailed: false };
      } catch (recalcError) {
        console.error("Recalculation failed after date update:", recalcError);
        return { event, stats: { events_updated: 0, errors: [] }, recalcFailed: true };
      }
    },
    onSuccess: ({ event, stats, recalcFailed }) => {
      queryClient.invalidateQueries({ queryKey: ["timeline", analysisId] });
      queryClient.invalidateQueries({ queryKey: ["timeline-deadlines", analysisId] });
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[event.event_id];
        return next;
      });

      if (recalcFailed) {
        addToast("error", "Fecha guardada pero el recálculo de dependencias falló. Intenta recargar la página.");
        return;
      }
      if (stats.errors && stats.errors.length > 0) {
        addToast("error", `Fecha guardada pero ${stats.errors.length} evento(s) no se pudieron recalcular.`);
        return;
      }
      const message =
        stats.events_updated > 0
          ? `"${event.name}" guardada. Se calcularon ${stats.events_updated} evento(s) dependientes.`
          : `"${event.name}" guardada.`;
      addToast("success", message);
    },
    onError: (error: Error) => {
      addToast("error", error.message || "Error al guardar la fecha");
    },
  });

  const hideMutation = useMutation({
    mutationFn: ({ event, hidden }: { event: EventResponse; hidden: boolean }) =>
      setEventHidden(analysisId, event.event_id, hidden),
    onSuccess: (_, { event, hidden }) => {
      queryClient.invalidateQueries({ queryKey: ["timeline", analysisId] });
      addToast("success", hidden ? `"${event.name}" ocultado` : `"${event.name}" vuelve a estar visible`);
    },
    onError: (error: Error) => {
      addToast("error", error.message || "Error al cambiar la visibilidad del evento");
    },
  });

  if (anchorEvents.length === 0) {
    return null;
  }

  const handleSave = (event: EventResponse) => {
    const value = drafts[event.event_id];
    if (!value) {
      addToast("error", "Elegí una fecha primero");
      return;
    }
    saveMutation.mutate({ event, newDate: value });
  };

  return (
    <section
      className="flex flex-col gap-1 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-5 py-[18px]"
      data-testid="anchor-dates-panel"
    >
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2 border-0 bg-transparent p-0"
        aria-expanded={isExpanded}
        data-testid="anchor-dates-panel-toggle"
      >
        <span className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[rgba(0,153,219,.12)] text-[#0099DB]">
            <CalendarClock className="h-[15px] w-[15px]" />
          </span>
          <span className="font-display text-base font-semibold text-[#003C6B]">
            Fechas por cargar ({anchorEvents.length})
          </span>
        </span>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-[rgba(0,60,107,.55)]" />
        ) : (
          <ChevronDown className="h-4 w-4 text-[rgba(0,60,107,.55)]" />
        )}
      </button>

      {isExpanded ? (
        <>
          <p className="mb-1 mt-1.5 text-[13px] leading-[1.5] text-[rgba(0,60,107,.68)]">
            Cargá estas fechas una sola vez: el resto de los plazos que dependen de ellas se
            calculan solos.
          </p>
          <div className="mt-1.5 flex flex-col gap-2">
            {anchorEvents.map((event) => {
              const dependentCount = dependentCountByEventId[event.event_id] ?? 0;
              const dependentNames = dependentEventNamesByEventId?.[event.event_id] ?? [];
              const isSavingThis =
                saveMutation.isPending && saveMutation.variables?.event.event_id === event.event_id;
              const isHidingThis =
                hideMutation.isPending && hideMutation.variables?.event.event_id === event.event_id;
              const canViewSource =
                Boolean(onViewSource) && Boolean(event.source_document_id) && Boolean(event.source_page);
              return (
                <div
                  key={event.event_id}
                  className={`flex flex-wrap items-center gap-2.5 rounded-xl border border-[rgba(0,60,107,.12)] bg-[#F4F9FC] px-3.5 py-2.5 ${
                    event.hidden ? "opacity-50" : ""
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-semibold text-[#003C6B]">{event.name}</span>
                      {event.source_reference?.mencion_propia === false ? (
                        <span
                          title="El pliego no menciona este evento por sí mismo -- se creó porque otro evento depende de su fecha para calcularse."
                          aria-label="Evento inferido, sin mención propia en el pliego"
                          className="inline-flex shrink-0 items-center text-[rgba(0,60,107,.4)]"
                        >
                          <HelpCircle className="h-[13px] w-[13px]" />
                        </span>
                      ) : null}
                    </div>
                    <p className="truncate text-xs text-[rgba(0,60,107,.55)]">
                      {dependentNames.length > 0
                        ? `Usado por: ${dependentNames.join(", ")}`
                        : dependentCount === 1
                          ? "1 plazo depende de esta fecha"
                          : `${dependentCount} plazos dependen de esta fecha`}
                    </p>
                  </div>
                  <DatePicker
                    variant="pill"
                    value={drafts[event.event_id] ?? null}
                    onChange={(iso) => setDrafts((prev) => ({ ...prev, [event.event_id]: iso }))}
                    markedDates={buildMarkedDates(cachedEvents, event.event_id)}
                    placeholder="Elegir fecha"
                    aria-label={`Fecha de ${event.name}`}
                  />
                  <button
                    type="button"
                    onClick={() => handleSave(event)}
                    disabled={isSavingThis}
                    className="inline-flex h-[30px] items-center whitespace-nowrap rounded-full border-0 bg-[#003C6B] px-3.5 text-xs font-semibold text-white hover:bg-[#0099DB] disabled:opacity-50"
                  >
                    {isSavingThis ? "Guardando..." : "Guardar"}
                  </button>
                  {canViewSource ? (
                    <button
                      type="button"
                      onClick={() =>
                        onViewSource!(event.source_document_id!, event.source_page!, event.source_fragment)
                      }
                      title={`Ver fuente en el pliego (pág. ${event.source_page})`}
                      className="inline-flex h-[26px] items-center gap-[5px] rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2.5 text-[11px] font-semibold text-[#0099DB] hover:border-[#0099DB]"
                    >
                      <Eye className="h-3 w-3" />
                      pág. {event.source_page}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => hideMutation.mutate({ event, hidden: !event.hidden })}
                    disabled={isHidingThis}
                    title={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
                    aria-label={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
                    className="flex h-7 w-7 items-center justify-center rounded-lg border-0 bg-transparent text-[rgba(0,60,107,.4)] hover:bg-white hover:text-[#003C6B] disabled:opacity-50"
                  >
                    {event.hidden ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                  </button>
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </section>
  );
}
