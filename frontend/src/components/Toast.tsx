import { X } from "lucide-react";

import { cn } from "../utils/cn";

export type ToastType = "success" | "error";

interface ToastProps {
  id: string;
  type: ToastType;
  message: string;
  onClose: (id: string) => void;
}

export function Toast({ id, type, message, onClose }: ToastProps) {
  return (
    <div
      data-testid="toast"
      className={cn(
        "w-full min-w-[300px] max-w-[400px] animate-toast-in rounded-md border p-4 shadow-lg transition-all duration-200",
        type === "success" && "border-success bg-success-light text-green-900",
        type === "error" && "border-error bg-error-light text-red-900",
      )}
      role="status"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium">{message}</p>
        <button
          type="button"
          aria-label="Cerrar notificación"
          className="rounded-md p-1 hover:bg-black/10"
          onClick={() => onClose(id)}
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
