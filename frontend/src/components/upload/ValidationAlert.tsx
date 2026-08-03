import { AlertTriangle } from "lucide-react";

interface ValidationAlertProps {
  messages: string[];
}

export function ValidationAlert({ messages }: ValidationAlertProps) {
  if (messages.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2" role="alert" aria-live="polite">
      {messages.map((message) => (
        <div
          key={message}
          className="flex items-start gap-2 rounded-md border border-error bg-error-light p-3 text-sm text-red-700"
        >
          <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
          <p>{message}</p>
        </div>
      ))}
    </div>
  );
}
