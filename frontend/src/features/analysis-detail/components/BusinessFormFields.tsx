import type { ReactNode } from "react";

export const FIELD_CLASS =
  "h-11 w-full rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] text-sm text-[#003C6B] placeholder:text-[rgba(0,60,107,.45)] focus-visible:border-[#2F4EF8] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2F4EF8] disabled:cursor-not-allowed disabled:bg-gray-50";

export const SELECT_COMPACT_CLASS =
  "h-11 w-[74px] shrink-0 rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white pl-3.5 pr-1 text-[13px] font-semibold text-[#003C6B] focus-visible:border-[#2F4EF8] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2F4EF8]";

export const TEXTAREA_CLASS =
  "w-full resize-y rounded-2xl border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] py-3 text-sm text-[#003C6B] placeholder:text-[rgba(0,60,107,.45)] focus-visible:border-[#2F4EF8] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2F4EF8]";

export const SECTION_LABEL_CLASS =
  "text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]";

export const FIELD_LABEL_CLASS =
  "text-xs font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.55)]";

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  error?: string;
  children: ReactNode;
}

export function FormField({ label, htmlFor, error, children }: FormFieldProps) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      {htmlFor ? (
        <label htmlFor={htmlFor} className={FIELD_LABEL_CLASS}>
          {label}
        </label>
      ) : (
        <span className={FIELD_LABEL_CLASS}>{label}</span>
      )}
      {children}
      {error ? <p className="text-xs text-error">{error}</p> : null}
    </div>
  );
}

interface MoneyInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  symbol: string;
  placeholder?: string;
}

export function MoneyInput({ id, value, onChange, onBlur, symbol, placeholder = "0" }: MoneyInputProps) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-[18px] top-1/2 -translate-y-1/2 text-sm font-semibold text-[rgba(0,60,107,.55)]">
        {symbol}
      </span>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        className={`${FIELD_CLASS} ${symbol.length > 1 ? "pl-[52px]" : "pl-[36px]"}`}
      />
    </div>
  );
}
