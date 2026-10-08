import { useState, type MouseEvent } from "react";
import { ArrowRight } from "lucide-react";
import type { DeadlineResponse, EventResponse, HighlightRegion } from "../../types/timeline";
import { formatDeadlineDuration } from "../../utils/deadlineFormat";
import { DeadlineDetailModal } from "./DeadlineDetailModal";

interface DependencyIndicatorProps {
  deadline: DeadlineResponse;
  triggerEvent?: EventResponse;
  targetEvent?: EventResponse;
  onViewSource?: (documentId: string, page: number, fragment?: string, highlightRegions?: HighlightRegion[]) => void;
}

export function DependencyIndicator({
  deadline,
  triggerEvent,
  targetEvent,
  onViewSource,
}: DependencyIndicatorProps) {
  const [showDetail, setShowDetail] = useState(false);

  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setShowDetail(true);
  };

  // BUG real (Corrientes, 2026-10-02): un evento puede tener su PROPIA fecha ya
  // confirmada (detectada en el pliego o ingresada a mano) y, AL MISMO TIEMPO,
  // ser el target de un plazo cuyo disparador todavía no tiene fecha -- dos
  // extracciones distintas del mismo hito real (ej. "Presentación de la Oferta",
  // detectada directamente con fecha propia, vs. el plazo "Presentación de la
  // Oferta" disparado por "Fecha de Tope de Presentación de Ofertas", sin fecha
  // propia). En ese caso la fecha del evento NO depende de este plazo -- ya está
  // confirmada por su cuenta -- así que "Pendiente de fecha de X" es directamente
  // falso. Solo tiene sentido esa frase cuando la fecha del evento realmente SALIÓ
  // de este cálculo (`date_source === "calculated"`) o cuando ni siquiera tiene
  // fecha propia todavía.
  const targetDateIsIndependentOfThisDeadline =
    Boolean(targetEvent?.event_date) && targetEvent?.date_source !== "calculated";

  if (!triggerEvent || triggerEvent.event_date === null) {
    if (targetDateIsIndependentOfThisDeadline) {
      return null;
    }
    return (
      <>
        <button
          type="button"
          className="mt-2 flex w-full items-center gap-[6px] text-left text-[12.5px] text-[rgba(0,60,107,.68)] hover:text-[#003C6B]"
          onClick={handleClick}
        >
          <ArrowRight className="h-[13px] w-[13px] flex-shrink-0" />
          <span>Pendiente de fecha de {triggerEvent?.name?.trim() || "evento anterior"}</span>
        </button>

        {showDetail && (
          <DeadlineDetailModal
            deadline={deadline}
            triggerEvent={triggerEvent}
            targetEvent={targetEvent}
            open={showDetail}
            onClose={() => setShowDetail(false)}
            onViewSource={onViewSource}
          />
        )}
      </>
    );
  }

  return (
    <>
      <button
        type="button"
        className="mt-2 flex w-full items-center gap-[6px] text-left text-[12.5px] text-[rgba(0,60,107,.68)] hover:text-[#0099DB]"
        onClick={handleClick}
      >
        <ArrowRight className="h-[13px] w-[13px] flex-shrink-0" />
        <span>
          {formatDeadlineDuration(deadline)} desde {triggerEvent.name?.trim() || "evento"}
        </span>
      </button>

      {showDetail && (
        <DeadlineDetailModal
          deadline={deadline}
          triggerEvent={triggerEvent}
          targetEvent={targetEvent}
          open={showDetail}
          onClose={() => setShowDetail(false)}
          onViewSource={onViewSource}
        />
      )}
    </>
  );
}
