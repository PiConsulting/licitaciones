import { useState } from "react";
import { CalendarClock, ChevronDown, ChevronUp, Eye, EyeOff, HelpCircle } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Badge } from "../Badge";
import { Button } from "../Button";
import { updateEvent, recalculateDependentDates, setEventHidden } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import type { EventResponse } from "../../types/timeline";

interface AnchorDatesPanelProps {
  analysisId: string;
  /** Eventos pendientes que son disparadores de al menos un plazo -- las
   * "fechas ancla" que hay que cargar para que el resto se calcule solo. */
  anchorEvents: EventResponse[];
  /** Cuántos plazos dependen de cada evento, para el texto de ayuda. */
  dependentCountByEventId: Record<string, number>;
  /** Nombres de los eventos que dependen de cada ancla (lo usan como
   * evento_disparador) -- se muestran en vez del conteo genérico cuando
   * están disponibles. */
  dependentEventNamesByEventId?: Record<string, string[]>;
  /** Abre el highlight del PDF de donde salió el evento, si tiene fuente. */
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

/**
 * Panel compacto para cargar las fechas "ancla" del Timeline: eventos sin
 * fecha de los que dependen uno o más plazos relativos. Es la contraparte
 * chica y rápida de las cards de "Eventos Pendientes" -- una fila por
 * evento, con su propio input de fecha, sin ocupar media pantalla.
 */
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
      className="mb-6 rounded-lg border border-blue-200 bg-blue-50/50 p-3"
      data-testid="anchor-dates-panel"
    >
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between gap-1.5"
        aria-expanded={isExpanded}
        data-testid="anchor-dates-panel-toggle"
      >
        <span className="flex items-center gap-1.5">
          <CalendarClock className="h-4 w-4 text-blue-700" />
          <h3 className="text-sm font-semibold text-blue-900">
            Fechas por cargar ({anchorEvents.length})
          </h3>
        </span>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-blue-700" />
        ) : (
          <ChevronDown className="h-4 w-4 text-blue-700" />
        )}
      </button>

      {isExpanded ? (
        <>
          <p className="mb-2 mt-2 text-xs text-blue-800">
            Cargá estas fechas una sola vez: el resto de los plazos que dependen de ellas se
            calculan solos.
          </p>
          <div className="space-y-1.5">
            {anchorEvents.map((event) => {
              const dependentCount = dependentCountByEventId[event.event_id] ?? 0;
              const dependentNames = dependentEventNamesByEventId?.[event.event_id] ?? [];
              const isSavingThis =
                saveMutation.isPending && saveMutation.variables?.event.event_id === event.event_id;
              const isHidingThis =
                hideMutation.isPending && hideMutation.variables?.event.event_id === event.event_id;
              return (
                <div
                  key={event.event_id}
                  className={`flex flex-wrap items-center gap-2 rounded-md border border-blue-100 bg-white px-2.5 py-1.5 ${
                    event.hidden ? "opacity-50" : ""
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 truncate text-sm font-medium text-gray-900">
                      {event.name}
                      {event.hidden ? (
                        <Badge tone="neutral" className="px-1.5 py-0.5 text-[10px]">
                          Oculto
                        </Badge>
                      ) : null}
                      {event.source_reference?.mencion_propia === false ? (
                        <span
                          title="El pliego no menciona este evento por sí mismo -- se creó porque otro evento depende de su fecha para calcularse."
                          aria-label="Evento inferido, sin mención propia en el pliego"
                          className="inline-flex shrink-0 items-center text-gray-400"
                        >
                          <HelpCircle className="h-3.5 w-3.5" />
                        </span>
                      ) : null}
                    </p>
                    <p className="truncate text-xs text-gray-500">
                      {dependentNames.length > 0
                        ? `Usado por: ${dependentNames.join(", ")}`
                        : dependentCount === 1
                          ? "1 plazo depende de esta fecha"
                          : `${dependentCount} plazos dependen de esta fecha`}
                    </p>
                  </div>
                  <input
                    type="date"
                    value={drafts[event.event_id] ?? ""}
                    onChange={(e) =>
                      setDrafts((prev) => ({ ...prev, [event.event_id]: e.target.value }))
                    }
                    className="h-7 w-[9.5rem] rounded-md border border-gray-200 px-1.5 text-xs focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                    aria-label={`Fecha de ${event.name}`}
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    className="whitespace-nowrap text-xs"
                    onClick={() => handleSave(event)}
                    loading={isSavingThis}
                  >
                    Guardar
                  </Button>
                  {onViewSource && event.source_document_id && event.source_page ? (
                    <button
                      onClick={() =>
                        onViewSource(event.source_document_id!, event.source_page!, event.source_fragment)
                      }
                      className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600"
                      title={`Ver fuente de ${event.name}`}
                      aria-label={`Ver fuente de ${event.name}`}
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Ver fuente
                    </button>
                  ) : null}
                  <button
                    onClick={() => hideMutation.mutate({ event, hidden: !event.hidden })}
                    disabled={isHidingThis}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 disabled:opacity-50"
                    title={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
                    aria-label={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
                  >
                    {event.hidden ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                    {event.hidden ? "Mostrar" : "Ocultar"}
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
