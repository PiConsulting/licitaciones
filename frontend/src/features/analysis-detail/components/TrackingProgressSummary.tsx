import type { AnalysisTracking } from "../../../types/tracking";

export type TrackingFilter = "all" | "pending" | "issues" | "closed";

export function trackingFilterCount(tracking: AnalysisTracking, filter: TrackingFilter): number {
  if (filter === "all") {
    return tracking.categories.length;
  }
  if (filter === "closed") {
    return tracking.categories.filter((category) => category.status === "closed").length;
  }
  if (filter === "issues") {
    return tracking.categories.filter((category) => category.items.some((item) => item.status === "non_compliant"))
      .length;
  }
  return tracking.categories.filter(
    (category) => category.status !== "closed" && category.items.some((item) => item.status === "not_evaluated"),
  ).length;
}

interface ComplianceFiltersProps {
  tracking: AnalysisTracking;
  filter: TrackingFilter;
  onFilterChange: (filter: TrackingFilter) => void;
}

const FILTERS: Array<{ key: TrackingFilter; label: string }> = [
  { key: "all", label: "Todas" },
  { key: "pending", label: "Con pendientes" },
  { key: "issues", label: "Con incumplimientos" },
  { key: "closed", label: "Cerradas" },
];

export function ComplianceFilters({ tracking, filter, onFilterChange }: ComplianceFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {FILTERS.map((pill) => {
        const isActive = filter === pill.key;
        return (
          <button
            key={pill.key}
            type="button"
            aria-pressed={isActive}
            onClick={() => onFilterChange(pill.key)}
            className={`inline-flex h-[34px] items-center gap-2 rounded-full border-[1.5px] px-3.5 text-[13px] font-semibold transition-colors ${
              isActive
                ? "border-[#003C6B] bg-[#003C6B] text-white"
                : "border-[rgba(0,60,107,.2)] bg-white text-[#003C6B] hover:border-[#0099DB]"
            }`}
          >
            <span>{pill.label}</span>
            <span className="font-medium opacity-80">{trackingFilterCount(tracking, pill.key)}</span>
          </button>
        );
      })}
    </div>
  );
}

interface ComplianceOverviewProps {
  tracking: AnalysisTracking;
}

export function ComplianceOverview({ tracking }: ComplianceOverviewProps) {
  const summary = tracking.summary;

  const allItems = tracking.categories.flatMap((category) => category.items);
  const compliant = allItems.filter((item) => item.status === "compliant").length;
  const nonCompliant = allItems.filter((item) => item.status === "non_compliant").length;
  const notApplicable = allItems.filter((item) => item.status === "not_applicable").length;
  const notEvaluated = allItems.filter((item) => item.status === "not_evaluated").length;
  const totalItems = allItems.length;
  const evaluatedItems = totalItems - notEvaluated;
  const evaluatedPct = totalItems > 0 ? Math.round((evaluatedItems / totalItems) * 100) : 0;

  const stackedWidth = (value: number) => (totalItems > 0 ? `${(value / totalItems) * 100}%` : "0%");

  return (
    <section aria-label="Avance" aria-live="polite" className="grid gap-3 xl:grid-cols-[minmax(260px,1.4fr)_repeat(4,minmax(120px,1fr))]">
      <div className="flex flex-col gap-3 rounded-2xl bg-[#003C6B] px-5 py-4 text-white">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#7FF3DE]">Avance general</span>
          <span className="text-xs text-white/75">{`${evaluatedItems} de ${totalItems} ítems evaluados`}</span>
        </div>
        <div className="flex items-baseline gap-2.5">
          <span className="font-display text-[40px] font-bold leading-none tracking-[-0.03em]">{`${evaluatedPct}%`}</span>
          <span className="text-[13px] text-white/75">{`${summary.closed} de ${summary.total_categories} categorías cerradas`}</span>
        </div>
        <div className="flex h-1.5 overflow-hidden rounded-full bg-white/20">
          <span className="bg-[#7FF3DE]" style={{ width: stackedWidth(compliant) }} />
          <span className="bg-[#FF6B6B]" style={{ width: stackedWidth(nonCompliant) }} />
          <span className="bg-white/45" style={{ width: stackedWidth(notApplicable) }} />
        </div>
      </div>

      {[
        { label: "Cumple", value: compliant, dot: "bg-[#1FC9A8]" },
        { label: "No cumple", value: nonCompliant, dot: "bg-[#DC2626]" },
        { label: "No aplica", value: notApplicable, dot: "bg-[rgba(0,60,107,.35)]" },
        { label: "Sin evaluar", value: notEvaluated, dot: "bg-[#A966FF]" },
      ].map((kpi) => (
        <article key={kpi.label} className="flex flex-col gap-2.5 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-5 py-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">{kpi.label}</span>
            <span className={`h-2 w-2 rounded-full ${kpi.dot}`} aria-hidden="true" />
          </div>
          <span className="font-display text-[32px] font-bold leading-none tracking-[-0.03em] text-[#003C6B]">{kpi.value}</span>
        </article>
      ))}
    </section>
  );
}
