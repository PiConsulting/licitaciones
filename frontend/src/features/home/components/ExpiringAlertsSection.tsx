import { AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { BUSINESS_STATUS_META, resolveBusinessStatus } from "../../analysis-detail/utils/businessStatus";
import type { ExpiringAlertItem } from "../hooks/useExpiringAlerts";

interface ExpiringAlertsSectionProps {
  alerts: ExpiringAlertItem[];
  onOpenAlert?: (alert: ExpiringAlertItem) => void;
}

const UNIT_DOT_COLORS: Record<string, string> = {
  CEDI: "#0099DB",
  PI: "#003C6B",
  Wemox: "#2F4EF8",
  Vulps: "#A966FF",
  Korex: "#7FF3DE",
};

const URGENT_DAYS_THRESHOLD = 2;

function daysBadgeStyle(daysUntil: number): { background: string; color: string } {
  if (daysUntil <= URGENT_DAYS_THRESHOLD) {
    return { background: "#E5484D", color: "#FFFFFF" };
  }
  return { background: "#F0731A", color: "#FFFFFF" };
}

function describeDays(daysUntil: number): { value: string; unit: string } {
  if (daysUntil === 0) {
    return { value: "Hoy", unit: "" };
  }
  return { value: String(daysUntil), unit: daysUntil === 1 ? "día" : "días" };
}

interface ScrollState {
  overflow: boolean;
  canPrev: boolean;
  canNext: boolean;
}

export function ExpiringAlertsSection({ alerts, onOpenAlert }: ExpiringAlertsSectionProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [scrollState, setScrollState] = useState<ScrollState>({
    overflow: false,
    canPrev: false,
    canNext: false,
  });

  const updateScrollState = useCallback(() => {
    const track = trackRef.current;
    if (!track) {
      return;
    }
    const overflow = track.scrollWidth > track.clientWidth + 1;
    setScrollState({
      overflow,
      canPrev: overflow && track.scrollLeft > 1,
      canNext: overflow && track.scrollLeft + track.clientWidth < track.scrollWidth - 1,
    });
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) {
      return undefined;
    }
    updateScrollState();
    track.addEventListener("scroll", updateScrollState);
    window.addEventListener("resize", updateScrollState);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateScrollState);
    observer?.observe(track);
    return () => {
      track.removeEventListener("scroll", updateScrollState);
      window.removeEventListener("resize", updateScrollState);
      observer?.disconnect();
    };
  }, [alerts.length, updateScrollState]);

  const scrollByPage = (direction: 1 | -1) => {
    const track = trackRef.current;
    if (!track) {
      return;
    }
    track.scrollBy?.({ left: direction * Math.max(track.clientWidth * 0.8, 280), behavior: "smooth" });
  };

  if (alerts.length === 0) {
    return null;
  }

  return (
    <section
      aria-label="Próximos eventos"
      className="flex flex-col gap-3 rounded-2xl border border-[rgba(169,102,255,.4)] bg-[rgba(169,102,255,.07)] px-5 py-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            className="inline-flex h-[30px] w-[30px] items-center justify-center rounded-full bg-[#A966FF] text-white"
            aria-hidden="true"
          >
            <AlertTriangle className="h-[15px] w-[15px]" strokeWidth={2.5} />
          </span>
          <div>
            <h2 className="font-display text-base font-bold text-cedi-navy">
              {alerts.length} {alerts.length === 1 ? "licitación con eventos próximos" : "licitaciones con eventos próximos"}
            </h2>
            <p className="mt-0.5 text-xs text-cedi-navy-68">
              En revisión y presentadas con eventos dentro de los próximos 15 días.
            </p>
          </div>
        </div>

        {scrollState.overflow ? (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => scrollByPage(-1)}
              disabled={!scrollState.canPrev}
              aria-label="Alertas anteriores"
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white text-cedi-navy transition-colors hover:border-[#A966FF] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-[rgba(0,60,107,.2)]"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => scrollByPage(1)}
              disabled={!scrollState.canNext}
              aria-label="Más alertas"
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white text-cedi-navy transition-colors hover:border-[#A966FF] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-[rgba(0,60,107,.2)]"
            >
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        ) : null}
      </div>

      <div
        ref={trackRef}
        data-testid="expiring-alerts-track"
        className="flex snap-x snap-mandatory gap-2.5 overflow-x-auto scroll-smooth [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {alerts.map((alert) => {
          const days = describeDays(alert.daysUntil);
          const statusMeta = alert.businessStatus ? BUSINESS_STATUS_META[resolveBusinessStatus(alert.businessStatus)] : null;
          const unitColor = alert.businessUnit ? (UNIT_DOT_COLORS[alert.businessUnit] ?? "#0099DB") : null;

          return (
            <button
              key={alert.id}
              type="button"
              onClick={() => onOpenAlert?.(alert)}
              data-testid={`expiring-alert-${alert.id}`}
              aria-label={`Ver timeline de ${alert.analysisName}: ${alert.eventName}`}
              className="flex w-[300px] flex-none snap-start items-start gap-3.5 rounded-xl border border-cedi-navy-12 bg-white px-3.5 py-3 text-left text-cedi-navy transition-colors hover:border-[#A966FF]"
            >
              <div
                data-testid={`expiring-days-${alert.id}`}
                style={daysBadgeStyle(alert.daysUntil)}
                className="min-w-[56px] shrink-0 rounded-[10px] px-1.5 py-2 text-center"
              >
                <div className="font-display text-2xl font-bold leading-none">{days.value}</div>
                {days.unit ? (
                  <div className="mt-[3px] text-[10px] font-bold uppercase tracking-[0.08em]">{days.unit}</div>
                ) : null}
              </div>

              <div className="flex min-w-0 flex-col gap-1">
                <p className="line-clamp-2 text-[13px] font-semibold leading-[1.35]">{alert.analysisName}</p>
                {alert.organismo ? (
                  <p className="line-clamp-1 text-xs text-cedi-navy-68">{alert.organismo}</p>
                ) : null}
                <p className="line-clamp-2 text-xs font-semibold text-cedi-navy">
                  {alert.eventName}
                  <span className="font-normal text-cedi-navy-55"> · {alert.dateLabel}</span>
                  {alert.additionalEvents > 0 ? (
                    <span className="font-normal text-cedi-navy-55"> · +{alert.additionalEvents} más</span>
                  ) : null}
                </p>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                  {statusMeta ? (
                    <span
                      className="inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold"
                      style={{ background: statusMeta.bg, color: statusMeta.fg }}
                    >
                      {statusMeta.label}
                    </span>
                  ) : null}
                  {alert.businessUnit && unitColor ? (
                    <span className="inline-flex items-center gap-[5px] text-[11px] font-semibold">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: unitColor }} aria-hidden="true" />
                      {alert.businessUnit}
                    </span>
                  ) : null}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
