import type { DatePreset } from "../hooks/useAnalysisFilters";

interface DateRangeFilterProps {
  preset: DatePreset;
  dateFrom: string;
  dateTo: string;
  onPresetChange: (preset: DatePreset) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
}

export function DateRangeFilter({
  preset,
  dateFrom,
  dateTo,
  onPresetChange,
  onDateFromChange,
  onDateToChange,
}: DateRangeFilterProps) {
  const options: Array<{ value: DatePreset; label: string }> = [
    { value: "all", label: "Todo" },
    { value: "last_30_days", label: "Últimos 30 días" },
    { value: "current_quarter", label: "Este trimestre" },
    { value: "custom", label: "Personalizado" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filtro de fecha">
        {options.map((option) => {
          const isActive = preset === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onPresetChange(option.value)}
              className={[
                "inline-flex h-9 items-center justify-center whitespace-nowrap rounded-full border-[1.5px] px-3.5 text-[13px] font-semibold leading-none transition",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cedi-electric",
                isActive
                  ? "border-cedi-navy bg-cedi-navy text-white"
                  : "border-cedi-navy-20 bg-white text-cedi-navy hover:border-cedi-navy-30",
              ].join(" ")}
              aria-pressed={isActive}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      {preset === "custom" ? (
        <div className="ml-1 flex flex-wrap items-center gap-1.5">
          <label className="sr-only" htmlFor="date-from-filter">
            Desde
          </label>
          <input
            id="date-from-filter"
            type="date"
            value={dateFrom}
            onChange={(event) => onDateFromChange(event.target.value)}
            className="h-9 rounded-full border-[1.5px] border-cedi-navy-20 bg-white px-3.5 text-[13px] text-cedi-navy focus-visible:border-cedi-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-cedi-electric"
          />

          <span className="text-[13px] text-cedi-navy-55">-</span>

          <label className="sr-only" htmlFor="date-to-filter">
            Hasta
          </label>
          <input
            id="date-to-filter"
            type="date"
            value={dateTo}
            onChange={(event) => onDateToChange(event.target.value)}
            className="h-9 rounded-full border-[1.5px] border-cedi-navy-20 bg-white px-3.5 text-[13px] text-cedi-navy focus-visible:border-cedi-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-cedi-electric"
          />
        </div>
      ) : null}
    </div>
  );
}
