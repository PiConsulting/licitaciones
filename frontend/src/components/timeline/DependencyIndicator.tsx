import { useState, type MouseEvent } from "react";
import { ArrowRight } from "lucide-react";
import type { DeadlineResponse, EventResponse } from "../../types/timeline";
import { DeadlineDetailModal } from "./DeadlineDetailModal";

interface DependencyIndicatorProps {
  deadline: DeadlineResponse;
  triggerEvent?: EventResponse;
  targetEvent?: EventResponse;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DAY_TYPE_LABEL: Record<string, string> = {
  corridos: "corridos",
  hábiles: "hábiles",
  no_especificado: "(tipo no especificado)",
};

export function DependencyIndicator({
  deadline,
  triggerEvent,
  targetEvent,
  onViewSource,
}: DependencyIndicatorProps) {
  const [showDetail, setShowDetail] = useState(false);
  const dayTypeLabel = DAY_TYPE_LABEL[deadline.day_type] || deadline.day_type;

  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setShowDetail(true);
  };

  if (!triggerEvent || triggerEvent.event_date === null) {
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
          {deadline.duration} días {dayTypeLabel} desde {triggerEvent.name?.trim() || "evento"}
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
