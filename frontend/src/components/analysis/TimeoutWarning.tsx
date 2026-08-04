import { AlertTriangle } from "lucide-react";

interface TimeoutWarningProps {
  show: boolean;
}

export function TimeoutWarning({ show }: TimeoutWarningProps) {
  if (!show) {
    return null;
  }

  return (
    <div className="flex items-start gap-2 rounded-md border border-yellow-200 bg-yellow-50 p-3">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-600" />
      <p className="text-sm text-yellow-800">
        El analisis esta demorando mas de lo esperado pero continua procesandose
      </p>
    </div>
  );
}
