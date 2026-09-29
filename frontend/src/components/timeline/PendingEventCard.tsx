import { AlertTriangle, ArrowRight, Calendar, Eye, HelpCircle } from "lucide-react";
import { Event, DeadlineResponse, EventResponse } from "../../types/timeline";
import { ErrorIndicator } from "./ErrorIndicator";

interface PendingEventCardProps {
  event: Event;
  hasDependents?: boolean;
  dependentEventNames?: string[];
  deadline?: DeadlineResponse;
  triggerEvent?: EventResponse;
  onAddDate: () => void;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DAY_TYPE_LABEL: Record<string, string> = {
  corridos: "corridos",
  hábiles: "hábiles",
  no_especificado: "(tipo de día no especificado)",
};

export function PendingEventCard({
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
  const isWarning = deadline?.day_type === "no_especificado";
  const hasCalculationError = deadline?.calculation_status === "error" && deadline.calculation_error;

  return (
    <article
      className={`pending-event-card flex flex-col gap-2 rounded-2xl border border-dashed border-[rgba(0,60,107,.22)] bg-[#F4F9FC] px-[18px] py-[14px] ${
        event.hidden ? "opacity-50" : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-[10px]">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h3 className="font-display text-[15px] font-semibold text-[#003C6B]">{event.name}</h3>
          {isInferred ? (
            <span
              title="El pliego no menciona este evento por sí mismo -- se creó porque otro evento depende de su fecha para calcularse."
              aria-label="Evento inferido, sin mención propia en el pliego"
              className="inline-flex shrink-0 items-center text-[rgba(0,60,107,.35)]"
            >
              <HelpCircle className="h-[13px] w-[13px]" />
            </span>
          ) : null}
          <span className="inline-flex items-center rounded-full bg-[rgba(0,60,107,.08)] px-2.5 py-[3px] text-[11px] font-bold text-[rgba(0,60,107,.68)]">
            Pendiente
          </span>
        </div>
        <div className="flex flex-shrink-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onAddDate}
            className="inline-flex h-[30px] items-center gap-1.5 whitespace-nowrap rounded-full border-[1.5px] border-[#003C6B] bg-white px-3 text-xs font-semibold text-[#003C6B] hover:bg-[#003C6B] hover:text-white"
          >
            <Calendar className="h-[13px] w-[13px]" />
            Agregar fecha
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
        </div>
      </div>

      {isWarning ? (
        <div className="flex items-start gap-1.5 rounded-[10px] bg-[rgba(169,102,255,.1)] px-2.5 py-2 text-[12.5px] leading-[1.5] text-[#6E2FC9]">
          <AlertTriangle className="mt-[1px] h-3.5 w-3.5 flex-shrink-0" />
          <span>
            El pliego no especifica si son días hábiles o corridos ({deadline!.duration} días desde{" "}
            <span className="font-medium">{triggerEvent?.name?.trim() || "otro evento"}</span>) — no se
            puede calcular sola, cargá la fecha a mano.
          </span>
        </div>
      ) : hasCalculationError ? (
        <ErrorIndicator error={deadline!.calculation_error!} />
      ) : deadline ? (
        <div className="flex items-center gap-[6px] text-[12.5px] text-[rgba(0,60,107,.68)]">
          <ArrowRight className="h-[13px] w-[13px] flex-shrink-0" />
          <span>
            Se calcula: {deadline.duration} días {dayTypeLabel} desde{" "}
            <span className="font-medium">{triggerEvent?.name?.trim() || "otro evento"}</span>
            {triggerEvent?.event_date ? null : " (todavía sin fecha)"}
          </span>
        </div>
      ) : (
        <p className="text-[12.5px] text-[rgba(0,60,107,.55)]">Fecha pendiente</p>
      )}

      {hasDependents ? (
        <div className="flex items-center gap-[6px] text-[12.5px] text-[#B45309]">
          <AlertTriangle className="h-[13px] w-[13px] flex-shrink-0" />
          <span>
            {dependentEventNames && dependentEventNames.length > 0
              ? `Usado por: ${dependentEventNames.join(", ")}`
              : "Otros eventos dependen de esta fecha"}
          </span>
        </div>
      ) : null}
    </article>
  );
}
