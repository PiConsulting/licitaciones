interface TimelineStatsProps {
  totalEvents: number;
  confirmedEvents: number;
  pendingEvents: number;
  completedEvents: number;
  nextUpcomingEvent?: {
    name: string;
    date: string;
  } | null;
}

export function TimelineStats({
  totalEvents,
  completedEvents,
  nextUpcomingEvent,
}: TimelineStatsProps) {
  const safeTotal = Math.max(totalEvents, 0);
  const safeCompleted = Math.min(Math.max(completedEvents, 0), safeTotal);

  const formatShortDate = (isoDate: string) => {
    const [year, month, day] = isoDate.split("-");
    if (!year || !month || !day) {
      return isoDate;
    }
    return `${day}/${month}`;
  };

  const getDaysUntil = (isoDate: string) => {
    const today = new Date();
    const target = new Date(`${isoDate}T00:00:00`);
    const nowLocal = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const diffMs = target.getTime() - nowLocal.getTime();
    return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
  };

  const nextDueLabel = nextUpcomingEvent ? `${getDaysUntil(nextUpcomingEvent.date)} días` : "Sin fecha";
  const nextDueDetail = nextUpcomingEvent
    ? `${nextUpcomingEvent.name} · ${formatShortDate(nextUpcomingEvent.date)}`
    : "No hay hitos futuros confirmados";

  return (
    <div className="timeline-stats mb-4 grid grid-cols-1 gap-3 md:grid-cols-3" data-testid="timeline-stats">
      <article className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-[18px] py-[14px]">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">Hitos</p>
          <p className="mt-[6px] font-display text-[28px] font-bold leading-none tracking-[-0.02em] text-[#003C6B]">
            {safeTotal}
          </p>
        </div>
      </article>

      <article className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-[18px] py-[14px]">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">Cumplidos</p>
          <p className="mt-[6px] font-display text-[28px] font-bold leading-none tracking-[-0.02em] text-[#0B6B58]">
            {safeCompleted}
          </p>
        </div>
      </article>

      <article className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-[#003C6B] px-[18px] py-[14px] text-white">
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#7FF3DE]">Próximo vencimiento</p>
        <p className="mt-[6px] font-display text-[28px] font-bold leading-none tracking-[-0.02em]">{nextDueLabel}</p>
        <p className="mt-1 text-xs text-[rgba(255,255,255,.75)]">{nextDueDetail}</p>
      </article>
    </div>
  );
}
