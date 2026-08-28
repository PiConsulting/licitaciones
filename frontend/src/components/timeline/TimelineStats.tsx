interface TimelineStatsProps {
  totalEvents: number;
  confirmedEvents: number;
  pendingEvents: number;
}

export function TimelineStats({
  totalEvents,
  confirmedEvents,
  pendingEvents,
}: TimelineStatsProps) {
  // Validar que confirmedEvents no exceda totalEvents (edge case de datos inconsistentes)
  const safeConfirmed = Math.min(confirmedEvents, totalEvents);
  const percentage = totalEvents > 0 ? Math.round((safeConfirmed / totalEvents) * 100) : 0;

  return (
    <div className="timeline-stats mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-blue-900">Estado de Timeline</h4>
          <p className="mt-1 text-sm text-blue-700">
            {safeConfirmed} de {totalEvents} eventos con fecha confirmada ({percentage}%)
          </p>
        </div>

        {pendingEvents > 0 && (
          <div className="text-sm text-blue-700">
            <span className="font-medium">{pendingEvents}</span> pendientes
          </div>
        )}
      </div>
    </div>
  );
}
