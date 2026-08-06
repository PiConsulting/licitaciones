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
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex min-w-44 flex-col gap-1">
        <span className="text-sm font-medium text-gray-700">Rango</span>
        <select
          value={preset}
          onChange={(event) => onPresetChange(event.target.value as DatePreset)}
          className="h-10 rounded-md border border-gray-200 px-3 py-2 text-sm focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        >
          <option value="all">Todas las fechas</option>
          <option value="last_week">Última semana</option>
          <option value="custom">Personalizado</option>
        </select>
      </label>

      <label className="flex min-w-40 flex-col gap-1">
        <span className="text-sm font-medium text-gray-700">Desde</span>
        <input
          type="date"
          value={dateFrom}
          onChange={(event) => onDateFromChange(event.target.value)}
          className="h-10 rounded-md border border-gray-200 px-3 py-2 text-sm focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        />
      </label>

      <label className="flex min-w-40 flex-col gap-1">
        <span className="text-sm font-medium text-gray-700">Hasta</span>
        <input
          type="date"
          value={dateTo}
          onChange={(event) => onDateToChange(event.target.value)}
          className="h-10 rounded-md border border-gray-200 px-3 py-2 text-sm focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        />
      </label>
    </div>
  );
}
