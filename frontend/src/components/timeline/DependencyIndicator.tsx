import { useState } from "react";
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

  const handleClick = () => {
    setShowDetail(true);
  };

  if (!triggerEvent || triggerEvent.event_date === null) {
    return (
      <>
        <div
          className="mt-2 flex items-center gap-2 text-sm text-gray-500 cursor-pointer hover:text-gray-700"
          onClick={handleClick}
        >
          <ArrowRight className="h-4 w-4" />
          <span>Pendiente de fecha de {triggerEvent?.name?.trim() || "evento anterior"}</span>
        </div>

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
      <div
        className="mt-2 flex items-center gap-2 text-sm text-gray-600 cursor-pointer hover:text-blue-600"
        onClick={handleClick}
      >
        <ArrowRight className="h-4 w-4" />
        <span>
          {deadline.duration} días {dayTypeLabel} desde {triggerEvent.name?.trim() || "evento"}
        </span>
      </div>

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
