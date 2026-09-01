import { useState } from "react";
import { Pencil, Trash2, HelpCircle, Eye, EyeOff } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Badge, BadgeTone } from "../Badge";
import { EventResponse, DateSource, DeadlineResponse } from "../../types/timeline";
import { DependencyIndicator } from "./DependencyIndicator";
import { ErrorIndicator } from "./ErrorIndicator";
import { EditDateModal } from "./EditDateModal";
import { DeleteEventDialog } from "./DeleteEventDialog";
import { EventDetailModal } from "./EventDetailModal";
import { formatEventDate } from "../../utils/dates";
import { setEventHidden } from "../../api/timeline";
import { useToast } from "../ToastContainer";

// Tipo refinado: evento con fecha confirmada (no null)
export type ConfirmedEvent = EventResponse & { event_date: string };

interface EventCardProps {
  analysisId: string;
  event: ConfirmedEvent;
  deadline?: DeadlineResponse;
  triggerEvent?: EventResponse;
  dependentDeadlines?: DeadlineResponse[]; // Plazos que tienen este evento como trigger
  /** Nombres de los eventos que dependen de este (lo usan como
   * evento_disparador), para mostrar en chiquito "Usado por: X, Y". */
  dependentEventNames?: string[];
  onClick?: () => void;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DATE_SOURCE_CONFIG: Record<DateSource, { label: string; tone: BadgeTone }> = {
  detected: { label: "Detectada", tone: "info" },
  user_input: { label: "Ingresada", tone: "success" },
  calculated: { label: "Calculada", tone: "warning" },
  pending: { label: "Pendiente", tone: "neutral" },
};

type ModalState = 'none' | 'detail' | 'edit' | 'delete';

export function EventCard({
  analysisId,
  event,
  deadline,
  triggerEvent,
  dependentDeadlines,
  dependentEventNames,
  onClick,
  onViewSource
}: EventCardProps) {
  const [activeModal, setActiveModal] = useState<ModalState>('none');
  const config = DATE_SOURCE_CONFIG[event.date_source];
  const hasCalculationError =
    deadline?.calculation_status === "error" && deadline.calculation_error;
  const isInferred = event.source_reference?.mencion_propia === false;

  const queryClient = useQueryClient();
  const { addToast } = useToast();

  // Ocultar/mostrar el evento sin borrarlo (2026-09-01) -- no necesita
  // confirmación (a diferencia del delete) porque es reversible con un
  // segundo click, así que la mutación va directo, sin modal.
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

  const handleCardClick = () => {
    if (onClick) {
      onClick();
    } else {
      setActiveModal('detail');
    }
  };

  const handleEditClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setActiveModal('edit');
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setActiveModal('delete');
  };

  const handleToggleHiddenClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    hideMutation.mutate(!event.hidden);
  };

  return (
    <>
      <div
        onClick={handleCardClick}
        className={`event-card rounded-lg border border-gray-200 px-3 py-2.5 transition-colors hover:bg-gray-50 cursor-pointer ${
          event.hidden ? "opacity-50" : ""
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              <h3 className="text-sm font-medium text-gray-900 truncate">{event.name}</h3>
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
              <span className="shrink-0 text-xs text-gray-500">{formatEventDate(event.event_date)}</span>
            </div>
            {dependentEventNames && dependentEventNames.length > 0 ? (
              <p className="mt-0.5 truncate text-xs text-gray-500">
                Usado por: {dependentEventNames.join(", ")}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-1">
            <Badge tone={config.tone} className="px-1.5 py-0.5 text-[10px]">
              {config.label}
            </Badge>
            <button
              onClick={handleEditClick}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
              title={`Editar fecha de ${event.name}`}
              aria-label={`Editar fecha de ${event.name}`}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleDeleteClick}
              className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
              title={`Eliminar evento ${event.name}`}
              aria-label={`Eliminar evento ${event.name}`}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleToggleHiddenClick}
              disabled={hideMutation.isPending}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors disabled:opacity-50"
              title={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
              aria-label={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
            >
              {event.hidden ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Mostrar error de cálculo si existe */}
        {hasCalculationError && (
          <div className="mt-2">
            <ErrorIndicator error={deadline.calculation_error!} />
          </div>
        )}

        {/* Dependency indicator solo si no hay error */}
        {deadline && !hasCalculationError && (
          <DependencyIndicator
            deadline={deadline}
            triggerEvent={triggerEvent}
            targetEvent={event}
            onViewSource={onViewSource}
          />
        )}
      </div>

      {/* Modal Detalle */}
      {activeModal === 'detail' && (
        <EventDetailModal
          event={event}
          deadlines={dependentDeadlines}
          open={true}
          onClose={() => setActiveModal('none')}
          onViewSource={onViewSource}
        />
      )}

      {/* Modal Editar Fecha */}
      {activeModal === 'edit' && (
        <EditDateModal
          event={event}
          open={true}
          onClose={() => setActiveModal('none')}
        />
      )}

      {/* Diálogo Eliminar Evento */}
      {activeModal === 'delete' && (
        <DeleteEventDialog
          event={event}
          open={true}
          onClose={() => setActiveModal('none')}
        />
      )}
    </>
  );
}
