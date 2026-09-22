import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "../utils/cn";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-cedi-gradient-button text-cedi-white hover:brightness-110",
  secondary: "bg-cedi-white text-cedi-navy border border-cedi-navy-20 hover:border-cedi-navy-30",
  danger: "bg-error text-white hover:bg-red-700",
  ghost: "bg-transparent text-cedi-celeste hover:text-cedi-navy hover:underline",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-6 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex min-w-[44px] items-center justify-center rounded-full font-semibold transition-all duration-200",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-cedi-electric active:scale-98",
        "disabled:cursor-not-allowed disabled:opacity-40",
        (disabled || loading) && "cursor-not-allowed opacity-40",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 data-testid="loader-icon" className="animate-spin" size={20} /> : children}
    </button>
  );
}
