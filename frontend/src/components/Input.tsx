import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";

import { cn } from "../utils/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, id, error, className, disabled, ...props },
  ref,
) {
  const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-gray-700">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={Boolean(error)}
        aria-describedby={errorId}
        disabled={disabled}
        className={cn(
          "h-10 rounded-full border border-cedi-navy-20 px-4 text-sm",
          "focus-visible:border-cedi-electric focus-visible:outline focus-visible:outline-2 focus-visible:outline-cedi-electric",
          "disabled:cursor-not-allowed disabled:bg-gray-50",
          disabled && "cursor-not-allowed bg-gray-50",
          error && "border-error",
          className,
        )}
        {...props}
      />
      {error ? (
        <p id={errorId} className="text-xs text-error">
          {error}
        </p>
      ) : null}
    </div>
  );
});
