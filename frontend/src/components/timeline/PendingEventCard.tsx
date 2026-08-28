import { AlertTriangle, Calendar } from "lucide-react";
import { Badge } from "../Badge";
import { Button } from "../Button";
import { Event } from "../../types/timeline";

interface PendingEventCardProps {
  event: Event;
  hasDependents?: boolean;
  onAddDate: () => void;
}

export function PendingEventCard({ event, hasDependents = false, onAddDate }: PendingEventCardProps) {
  return (
    <div className="pending-event-card rounded-lg border-2 border-dashed border-gray-300 bg-gray-50/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-medium text-gray-700">{event.name}</h3>
          <p className="mt-1 text-sm text-gray-500">Fecha pendiente</p>
          {hasDependents ? (
            <div className="mt-2 flex items-center gap-1.5 text-sm text-warning">
              <AlertTriangle className="h-4 w-4" />
              <span>Otros eventos dependen de esta fecha</span>
            </div>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2">
          <Badge tone="neutral">Pendiente</Badge>
          <Button variant="secondary" size="sm" onClick={onAddDate}>
            <Calendar className="mr-1.5 h-4 w-4" />
            Agregar fecha
          </Button>
        </div>
      </div>
    </div>
  );
}
