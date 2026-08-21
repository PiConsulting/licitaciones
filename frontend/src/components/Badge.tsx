import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../utils/cn";

export type BadgeTone = "success" | "warning" | "error" | "critical" | "highlight" | "info" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: "bg-success-light text-success",
  warning: "bg-warning-light text-warning",
  error: "bg-error-light text-error",
  critical: "bg-critical-light text-critical",
  highlight: "bg-highlight-light text-highlight",
  info: "bg-sky-100 text-sky-700",
  neutral: "bg-gray-100 text-gray-600",
};

interface BadgeProps {
  tone: BadgeTone;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
  title?: string;
}

export function Badge({ tone, icon: Icon, children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold uppercase",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
      {children}
    </span>
  );
}
