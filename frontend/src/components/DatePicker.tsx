import { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "../utils/cn";

interface DatePickerProps {
  value: string | null;
  onChange: (isoDate: string) => void;
  placeholder?: string;
  variant?: "pill" | "field";
  fullWidth?: boolean;
  markedDates?: Record<string, string[]>;
  className?: string;
  id?: string;
  "aria-label"?: string;
}

const WEEKDAYS = ["L", "M", "M", "J", "V", "S", "D"];
const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function toIso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function fromIso(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatDisplay(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function buildMonthGrid(viewDate: Date): (Date | null)[] {
  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const leadingBlanks = (firstDay.getDay() + 6) % 7;
  const cells: (Date | null)[] = [];
  for (let i = 0; i < leadingBlanks; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

export function DatePicker({
  value,
  onChange,
  placeholder = "Elegir fecha",
  variant = "field",
  fullWidth = false,
  markedDates,
  className,
  id,
  "aria-label": ariaLabel,
}: DatePickerProps) {
  const [open, setOpen] = useState(false);
  const [viewDate, setViewDate] = useState(() => (value ? fromIso(value) : new Date()));
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const handleOpen = () => {
    setViewDate(value ? fromIso(value) : new Date());
    setOpen((prev) => !prev);
  };

  const handlePick = (date: Date) => {
    onChange(toIso(date));
    setOpen(false);
  };

  const today = new Date();
  const selected = value ? fromIso(value) : null;
  const cells = buildMonthGrid(viewDate);

  const isSameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  return (
    <div ref={containerRef} className={cn("relative inline-block", fullWidth && "block w-full")}>
      {variant === "pill" ? (
        <button
          type="button"
          id={id}
          onClick={handleOpen}
          aria-label={ariaLabel}
          aria-expanded={open}
          className={cn(
            "inline-flex h-[30px] items-center justify-center whitespace-nowrap rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 text-xs font-semibold",
            value ? "text-[#003C6B]" : "text-[rgba(0,60,107,.55)]",
            className,
          )}
        >
          {value ? formatDisplay(value) : placeholder}
        </button>
      ) : (
        <button
          type="button"
          id={id}
          onClick={handleOpen}
          aria-label={ariaLabel}
          aria-expanded={open}
          className={cn(
            "relative flex h-[42px] w-full items-center rounded-xl border-[1.5px] border-[rgba(0,60,107,.2)] bg-white pl-[38px] pr-3.5 text-left text-sm",
            value ? "text-[#003C6B]" : "text-[rgba(0,60,107,.45)]",
            className,
          )}
        >
          <CalendarDays className="pointer-events-none absolute left-[13px] h-[15px] w-[15px] text-[rgba(0,60,107,.45)]" />
          {value ? formatDisplay(value) : placeholder}
        </button>
      )}

      {open ? (
        <div className="absolute left-0 top-[calc(100%+6px)] z-50 w-[280px] rounded-2xl border border-[rgba(0,60,107,.12)] bg-white p-3 shadow-[0_16px_40px_rgba(0,60,107,.2)]">
          <div className="flex items-center justify-between px-1">
            <button
              type="button"
              onClick={() => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1))}
              aria-label="Mes anterior"
              className="flex h-7 w-7 items-center justify-center rounded-lg text-[#003C6B] hover:bg-[#F4F9FC]"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="font-display text-[13px] font-semibold text-[#003C6B]">
              {MONTH_NAMES[viewDate.getMonth()]} {viewDate.getFullYear()}
            </span>
            <button
              type="button"
              onClick={() => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1))}
              aria-label="Mes siguiente"
              className="flex h-7 w-7 items-center justify-center rounded-lg text-[#003C6B] hover:bg-[#F4F9FC]"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-2 grid grid-cols-7 gap-1">
            {WEEKDAYS.map((day, i) => (
              <span
                key={`${day}-${i}`}
                className="flex h-6 items-center justify-center text-[11px] font-semibold text-[rgba(0,60,107,.45)]"
              >
                {day}
              </span>
            ))}
            {cells.map((date, i) => {
              if (!date) return <span key={`blank-${i}`} className="h-8 w-8" />;
              const isSelected = selected ? isSameDay(date, selected) : false;
              const isToday = isSameDay(date, today);
              const markedNames = markedDates?.[toIso(date)];
              const isMarked = Boolean(markedNames && markedNames.length > 0);
              const alignEnd = i % 7 >= 4;
              return (
                <div key={date.toISOString()} className="group relative">
                  <button
                    type="button"
                    onClick={() => handlePick(date)}
                    aria-label={isMarked ? `${date.getDate()}: ${markedNames?.join(", ")}` : undefined}
                    data-marked={isMarked ? "true" : undefined}
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full text-[12.5px] font-medium hover:bg-[#F4F9FC]",
                      isSelected
                        ? "bg-[#003C6B] font-semibold text-white hover:bg-[#003C6B]"
                        : isMarked
                          ? "bg-[rgba(169,102,255,.18)] font-semibold text-[#6E2FC9] hover:bg-[rgba(169,102,255,.3)]"
                          : isToday
                            ? "text-[#0099DB] font-semibold"
                            : "text-[#003C6B]",
                    )}
                  >
                    {date.getDate()}
                  </button>
                  {isMarked ? (
                    <span
                      role="tooltip"
                      data-testid={`date-marker-${toIso(date)}`}
                      className={cn(
                        "pointer-events-none absolute bottom-[calc(100%+4px)] z-[60] hidden w-max max-w-[200px] rounded-lg bg-[#003C6B] px-2.5 py-1.5 text-left text-[11.5px] font-medium leading-[1.35] text-white shadow-lg group-hover:block group-focus-within:block",
                        alignEnd ? "right-0" : "left-0",
                      )}
                    >
                      {markedNames?.map((name) => (
                        <span key={name} className="block">
                          {name}
                        </span>
                      ))}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => handlePick(today)}
            className="mt-2 w-full rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white py-1.5 text-xs font-semibold text-[#003C6B] hover:border-[#0099DB]"
          >
            Hoy
          </button>
        </div>
      ) : null}
    </div>
  );
}
