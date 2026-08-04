import type { LucideIcon } from "lucide-react";

import { cn } from "../../utils/cn";

type ActionButtonVariant = "warning" | "danger" | "ghost";

const VARIANT_CLASS: Record<ActionButtonVariant, string> = {
  warning: "bg-warning text-white hover:bg-warning/90",
  danger: "bg-error text-white hover:bg-error/90",
  ghost: "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50",
};

interface ActionButtonProps {
  text: string;
  icon: LucideIcon;
  variant: ActionButtonVariant;
  onClick?: () => void;
}

export function ActionButton({ text, icon: Icon, variant, onClick }: ActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex min-h-[36px] items-center gap-1 rounded-md px-3 py-1.5 text-xs font-semibold",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary",
        VARIANT_CLASS[variant],
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {text}
    </button>
  );
}
