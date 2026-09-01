import { AlertTriangle, ArrowRight, Calendar, Eye, EyeOff, HelpCircle } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Badge } from "../Badge";
import { Button } from "../Button";
import { Event, DeadlineResponse, EventResponse } from "../../types/timeline";
import { setEventHidden } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import { ErrorIndicator } from "./ErrorIndicator";

interface PendingEventCardProps {
  analysisId: string;
  event: Event;
  hasDependents?: boolean;
  /** Nombres de los eventos que dependen de este (lo usan como
   * evento_disparador), para mostrar en chiquito en vez de un genérico
   * "otros eventos dependen de esta fecha". */
  dependentEventNames?: string[];
  /** Si este evento es el resultado de un plazo relativo (ej. "15 días
   * corridos desde Adjudicación"), el deadline y el evento disparador
   * correspondientes -- para mostrar la fórmula en vez de un genérico
   * "Fecha pendiente". */
  deadline?: DeadlineResponse;
  triggerEvent?: EventResponse;
  onAddDate: () => void;
  /** Abre el highlight del PDF de donde salió este evento, si tiene fuente
   * registrada (source_document_id/source_page). Sin esto, un evento
   * pendiente no se puede verificar contra el pliego real. */
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DAY_TYPE_LABEL: Record<string, string> = {
  corridos: "corridos",
  hábiles: "hábiles",
  no_especificado: "(tipo de día no especificado)",
};

export function PendingEventCard({
  analysisId,
  event,
  hasDependents = false,
  dependentEventNames,
  deadline,
  triggerEvent,
  onAddDate,
  onViewSource,
}: PendingEventCardProps) {
  const dayTypeLabel = deadline ? DAY_TYPE_LABEL[deadline.day_type] || deadline.day_type : "";
  const canViewSource =
    Boolean(onViewSource) && Boolean(event.source_document_id) && Boolean(event.source_page);
  const isInferred = event.source_reference?.mencion_propia === false;

  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const hideMutation = useMutation({
    mutationFn: (hidden: boolean) => setEventHidden(analysisId, event.event_id, hidden),
    onSuccess: (_, hidden) => {
      queryClient.invalidateQueries({ queryKey: ["timeline", analysisId] });
      addToast("success", hidden ? `"${event.name}" ocultado` : `"${event.name}" vuelve a estar visible`);
    },
    onError: (error: Error) => {
      addToast("error", error.message || "Error al cambiar la visibilidad del evento");
    },
  });

  return (
    <div
      className={`pending-event-card rounded-lg border-2 border-dashed border-gray-300 bg-gray-50/50 px-3 py-2.5 ${
        event.hidden ? "opacity-50" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <h3 className="text-sm font-medium text-gray-800">{event.name}</h3>
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

          {deadline?.day_type === "no_especificado" ? (
            // 2026-09-01: el pliego no dice si el plazo es de días hábiles o
            // corridos -- el motor de cálculo no lo asume solo (a propósito,
            // para no arriesgar una fecha mal calculada), así que hace falta
            // cargar esta fecha a mano con "Agregar fecha".
            <div className="mt-1 flex items-center gap-1.5 text-xs text-warning">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>
                El pliego no especifica si son días hábiles o corridos ({deadline.duration} días desde{" "}
                <span className="font-medium">{triggerEvent?.name?.trim() || "otro evento"}</span>) --
                no se puede calcular sola, cargá la fecha a mano.
              </span>
            </div>
          ) : deadline?.calculation_status === "error" && deadline.calculation_error ? (
            <div className="mt-1">
              <ErrorIndicator error={deadline.calculation_error} />
            </div>
          ) : deadline ? (
            <div className="mt-1 flex items-center gap-1.5 text-xs text-gray-600">
              <ArrowRight className="h-3.5 w-3.5 shrink-0" />
              <span>
                Se calcula: {deadline.duration} días {dayTypeLabel} desde{" "}
                <span className="font-medium">{triggerEvent?.name?.trim() || "otro evento"}</span>
                {triggerEvent?.event_date ? null : " (todavía sin fecha)"}
              </span>
            </div>
          ) : (
            <p className="mt-0.5 text-xs text-gray-500">Fecha pendiente</p>
          )}

          {hasDependents ? (
            <div className="mt-1 flex items-center gap-1.5 text-xs text-warning">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>
                {dependentEventNames && dependentEventNames.length > 0
                  ? `Usado por: ${dependentEventNames.join(", ")}`
                  : "Otros eventos dependen de esta fecha"}
              </span>
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <Badge tone="neutral" className="px-1.5 py-0.5 text-[10px]">
            Pendiente
          </Badge>
          <Button variant="secondary" size="sm" className="whitespace-nowrap text-xs" onClick={onAddDate}>
            <Calendar className="mr-1 h-3.5 w-3.5" />
            Agregar fecha
          </Button>
          {canViewSource ? (
            <button
              onClick={() =>
                onViewSource!(event.source_document_id!, event.source_page!, event.source_fragment)
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
            onClick={() => hideMutation.mutate(!event.hidden)}
            disabled={hideMutation.isPending}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 disabled:opacity-50"
            title={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
            aria-label={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
          >
            {event.hidden ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            {event.hidden ? "Mostrar" : "Ocultar"}
          </button>
        </div>
      </div>
    </div>
  );
}
