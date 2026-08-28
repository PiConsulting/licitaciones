import { AlertCircle } from "lucide-react";

interface ErrorIndicatorProps {
  error: string;
}

export function ErrorIndicator({ error }: ErrorIndicatorProps) {
  return (
    <div className="error-indicator flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm">
      <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600" />
      <div className="text-red-800">
        <span className="font-medium">No se pudo calcular:</span> {error}
      </div>
    </div>
  );
}
