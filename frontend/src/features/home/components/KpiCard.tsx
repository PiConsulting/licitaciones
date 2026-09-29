interface KpiCardProps {
  label: string;
  value: number | string;
  dotColorClass: string;
  progressPercent: number;
  valueTestId: string;
  active?: boolean;
  showPercent?: boolean;
  onClick?: () => void;
}

export function KpiCard({
  label,
  value,
  dotColorClass,
  progressPercent,
  valueTestId,
  active = false,
  showPercent = true,
  onClick,
}: KpiCardProps) {
  const safePercent = Math.max(0, Math.min(100, progressPercent));

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "flex min-h-[118px] flex-col leading-[1.2] gap-[14px] rounded-2xl px-5 py-[18px] text-left transition-all duration-200",
        active
          ? "border-[1.5px] border-cedi-navy bg-cedi-navy text-white shadow-[0_8px_24px_rgba(0,60,107,0.18)]"
          : "border-[1.5px] border-cedi-navy-12 bg-white text-cedi-navy hover:border-cedi-celeste",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-2">
        <p className={active ? "whitespace-nowrap text-[11px] font-bold uppercase tracking-[0.14em] text-white/75" : "whitespace-nowrap text-[11px] font-bold uppercase tracking-[0.14em] text-cedi-navy-68"}>{label}</p>
        <span className={`h-2 w-2 rounded-full ${dotColorClass}`} aria-hidden="true" />
      </div>

      <div className="flex items-baseline gap-[10px]">
        <p
          className={active ? "font-display text-[36px] font-bold leading-none tracking-[-0.03em] text-white" : "font-display text-[36px] font-bold leading-none tracking-[-0.03em] text-cedi-navy"}
          data-testid={valueTestId}
        >
          {value}
        </p>
        {showPercent ? (
          <p className={active ? "text-[13px] font-semibold text-cedi-mint" : "text-[13px] font-semibold text-cedi-navy-55"}>
            {safePercent}%
          </p>
        ) : null}
      </div>

      <div className={active ? "h-[3px] overflow-hidden rounded-full bg-white/20" : "h-[3px] overflow-hidden rounded-full bg-cedi-navy-10"} aria-hidden="true">
        <div className={`h-full rounded-full ${dotColorClass}`} style={{ width: `${safePercent}%` }} />
      </div>
    </button>
  );
}
