import { CheckCircle2, AlertCircle, X } from "lucide-react";

import { cn } from "../utils/cn";

export type ToastType = "success" | "error";

interface ToastProps {
  id: string;
  type: ToastType;
  message: string;
  onClose: (id: string) => void;
}

const TONE = {
  success: { iconBg: "rgba(127,243,222,.35)", iconFg: "#0B6B58" },
  error: { iconBg: "#FEE2E2", iconFg: "#DC2626" },
};

export function Toast({ id, type, message, onClose }: ToastProps) {
  const tone = TONE[type];

  return (
    <div
      data-testid="toast"
      className={cn(
        "flex w-full min-w-[320px] max-w-[400px] animate-toast-in items-start gap-3 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white p-4 shadow-[0_16px_40px_rgba(0,60,107,.2)]",
      )}
      role="status"
    >
      <span
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full"
        style={{ background: tone.iconBg, color: tone.iconFg }}
      >
        {type === "success" ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
      </span>
      <p className="flex-1 pt-1 text-sm font-medium text-[#003C6B]">{message}</p>
      <button
        type="button"
        aria-label="Cerrar notificación"
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[rgba(0,60,107,.45)] hover:bg-[#F4F9FC] hover:text-[#003C6B]"
        onClick={() => onClose(id)}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
