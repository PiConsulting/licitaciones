import { AlertTriangle } from "lucide-react";

interface TimeoutWarningProps {
  show: boolean;
}

export function TimeoutWarning({ show }: TimeoutWarningProps) {
  if (!show) {
    return null;
  }

  return (
    <div className="flex items-start gap-2 rounded-2xl border border-[rgba(217,119,6,.3)] bg-[#FFFBEB] px-4 py-3">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[#B45309]" />
      <p className="text-sm text-[#B45309]">
        El análisis está demorando más de lo esperado pero continúa procesándose
      </p>
    </div>
  );
}
