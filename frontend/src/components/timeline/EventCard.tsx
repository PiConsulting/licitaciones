import { useState } from "react";
import { Pencil, Trash2, HelpCircle, Eye, EyeOff } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { EventResponse, DateSource, DeadlineResponse } from "../../types/timeline";
import { DependencyIndicator } from "./DependencyIndicator";
import { ErrorIndicator } from "./ErrorIndicator";
import { EditDateModal } from "./EditDateModal";
import { DeleteEventDialog } from "./DeleteEventDialog";
import { EventDetailModal } from "./EventDetailModal";
import { formatEventDate } from "../../utils/dates";
import { setEventHidden } from "../../api/timeline";
import { useToast } from "../ToastContainer";

export type ConfirmedEvent = EventResponse & { event_date: string };

interface EventCardProps {
  analysisId: string;
  event: ConfirmedEvent;
  deadline?: DeadlineResponse;
  triggerEvent?: EventResponse;
  dependentDeadlines?: DeadlineResponse[];
  dependentEventNames?: string[];
  isPast?: boolean;
  isNext?: boolean;
  onClick?: () => void;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DATE_SOURCE_CONFIG: Record<DateSource, { label: string; bg: string; fg: string }> = {
  detected: { label: "Detectada", bg: "rgba(0,153,219,.12)", fg: "#0077AD" },
  user_input: { label: "Ingresada", bg: "rgba(127,243,222,.35)", fg: "#0B6B58" },
  calculated: { label: "Calculada", bg: "rgba(169,102,255,.14)", fg: "#6E2FC9" },
  pending: { label: "Pendiente", bg: "rgba(0,60,107,.08)", fg: "rgba(0,60,107,.68)" },
};

type ModalState = 'none' | 'detail' | 'edit' | 'delete';

function getDaysUntil(isoDate: string): number {
  const today = new Date();
  const target = new Date(`${isoDate}T00:00:00`);
  const nowLocal = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.max(0, Math.ceil((target.getTime() - nowLocal.getTime()) / (1000 * 60 * 60 * 24)));
}

export function EventCard({
  analysisId,
  event,
  deadline,
  triggerEvent,
  dependentDeadlines,
  dependentEventNames,
  isPast = false,
  isNext = false,
  onClick,
  onViewSource
}: EventCardProps) {
  const [activeModal, setActiveModal] = useState<ModalState>('none');
  const sourceConfig = DATE_SOURCE_CONFIG[event.date_source];
  const hasCalculationError =
    deadline?.calculation_status === "error" && deadline.calculation_error;
  const isInferred = event.source_reference?.mencion_propia === false;
  const accentColor = isPast ? "#1FC9A8" : isNext ? "#0099DB" : "rgba(0,60,107,.12)";
  const canViewSource =
    Boolean(onViewSource) && Boolean(event.source_document_id) && Boolean(event.source_page);

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
        className={`event-card flex overflow-hidden rounded-2xl border border-[rgba(0,60,107,.12)] bg-white ${
          event.hidden ? "opacity-50" : ""
        }`}
      >
        <div className="w-1 flex-shrink-0" style={{ background: accentColor }} />
        <div
          onClick={handleCardClick}
          className="min-w-0 flex-1 cursor-pointer px-[18px] py-[14px]"
        >
          <div className="flex flex-wrap items-start justify-between gap-[10px]">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h3 className="font-display text-[15px] font-semibold text-[#003C6B]">{event.name}</h3>
              {event.hidden ? (
                <span className="inline-flex items-center rounded-full bg-[rgba(0,60,107,.08)] px-2.5 py-[3px] text-[11px] font-bold text-[rgba(0,60,107,.68)]">
                  Oculto
                </span>
              ) : null}
              {isInferred ? (
                <span
                  title="El pliego no menciona este evento por sí mismo -- se creó porque otro evento depende de su fecha para calcularse."
                  aria-label="Evento inferido, sin mención propia en el pliego"
                  className="inline-flex shrink-0 items-center text-[rgba(0,60,107,.35)]"
                >
                  <HelpCircle className="h-[13px] w-[13px]" />
                </span>
              ) : null}
              <span
                className="inline-flex items-center rounded-full px-2.5 py-[3px] text-[11px] font-bold"
                style={{ background: sourceConfig.bg, color: sourceConfig.fg }}
              >
                {sourceConfig.label}
              </span>
              {isPast ? (
                <span className="inline-flex items-center rounded-full bg-[rgba(127,243,222,.35)] px-2.5 py-[3px] text-[11px] font-bold text-[#0B6B58]">
                  Cumplido
                </span>
              ) : isNext ? (
                <span className="inline-flex items-center rounded-full bg-[#0099DB] px-2.5 py-[3px] text-[11px] font-bold text-white">
                  Próximo · en {getDaysUntil(event.event_date)} días
                </span>
              ) : null}
            </div>
            <div className="flex flex-shrink-0 items-center gap-[10px]">
              <span className="font-display whitespace-nowrap text-[13px] font-bold text-[#003C6B]">
                {formatEventDate(event.event_date)}
              </span>
              <div className="flex items-center gap-0.5">
                <button
                  onClick={handleEditClick}
                  className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border-0 bg-transparent text-[rgba(0,60,107,.4)] hover:bg-[#F4F9FC] hover:text-[#003C6B]"
                  title={`Editar fecha de ${event.name}`}
                  aria-label={`Editar fecha de ${event.name}`}
                >
                  <Pencil className="h-[13px] w-[13px]" />
                </button>
                <button
                  onClick={handleDeleteClick}
                  className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border-0 bg-transparent text-[rgba(0,60,107,.4)] hover:bg-[#FEE2E2] hover:text-[#DC2626]"
                  title={`Eliminar evento ${event.name}`}
                  aria-label={`Eliminar evento ${event.name}`}
                >
                  <Trash2 className="h-[13px] w-[13px]" />
                </button>
                <button
                  onClick={handleToggleHiddenClick}
                  disabled={hideMutation.isPending}
                  className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border-0 bg-transparent text-[rgba(0,60,107,.4)] hover:bg-[#F4F9FC] hover:text-[#003C6B] disabled:opacity-50"
                  title={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
                  aria-label={event.hidden ? `Mostrar evento ${event.name}` : `Ocultar evento ${event.name}`}
                >
                  {event.hidden ? <Eye className="h-[13px] w-[13px]" /> : <EyeOff className="h-[13px] w-[13px]" />}
                </button>
              </div>
            </div>
          </div>

          {event.detalle ? (
            <p className="mt-1 truncate text-[13px] text-[rgba(0,60,107,.68)]">{event.detalle}</p>
          ) : null}

          {dependentEventNames && dependentEventNames.length > 0 ? (
            <p className="mt-1 truncate text-xs text-[rgba(0,60,107,.68)]">
              Usado por: {dependentEventNames.join(", ")}
            </p>
          ) : null}

          {hasCalculationError && (
            <div className="mt-2">
              <ErrorIndicator error={deadline.calculation_error!} />
            </div>
          )}

          {deadline && !hasCalculationError && (
            <DependencyIndicator
              deadline={deadline}
              triggerEvent={triggerEvent}
              targetEvent={event}
              onViewSource={onViewSource}
            />
          )}

          {canViewSource ? (
            <div className="mt-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onViewSource!(event.source_document_id!, event.source_page!, event.source_fragment);
                }}
                title={`Ver fuente en el pliego (pág. ${event.source_page})`}
                className="inline-flex h-[26px] items-center gap-[5px] rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2.5 text-[11px] font-semibold text-[#0099DB] hover:border-[#0099DB]"
              >
                <Eye className="h-3 w-3" />
                pág. {event.source_page}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {activeModal === 'detail' && (
        <EventDetailModal
          event={event}
          deadlines={dependentDeadlines}
          open={true}
          onClose={() => setActiveModal('none')}
          onViewSource={onViewSource}
        />
      )}

      {activeModal === 'edit' && (
        <EditDateModal
          event={event}
          open={true}
          onClose={() => setActiveModal('none')}
        />
      )}

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
