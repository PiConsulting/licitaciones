import type { InputHTMLAttributes } from "react";

import { cn } from "../utils/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export function Input({ label, id, error, className, disabled, ...props }: InputProps) {
  const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  const errorId = error ? `${inputId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-gray-700">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={Boolean(error)}
        aria-describedby={errorId}
        disabled={disabled}
        className={cn(
          "h-10 rounded-md border border-gray-200 px-3 py-2.5 text-sm",
          "focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary",
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
}
