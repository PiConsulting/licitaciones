import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Button } from "../Button";
import { deleteEvent } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import type { EventResponse } from "../../types/timeline";

interface DeleteEventDialogProps {
  event: EventResponse;
  open: boolean;
  onClose: () => void;
}

export function DeleteEventDialog({ event, open, onClose }: DeleteEventDialogProps) {
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const wasDetected = event.date_source === "detected";

  const deleteMutation = useMutation({
    mutationFn: () => deleteEvent(event.analysis_id, event.event_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["timeline", event.analysis_id] });
      queryClient.invalidateQueries({ queryKey: ["timeline-deadlines", event.analysis_id] });
      addToast("success", "Evento eliminado");
      onClose();
    },
    onError: (error: Error) => {
      addToast("error", error.message || "Error al eliminar evento");
    },
  });

  const handleDelete = () => {
    deleteMutation.mutate();
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">Eliminar evento</h2>

        <div className="mt-4 space-y-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-red-800">
              <p className="font-medium">¿Eliminar &quot;{event.name}&quot;?</p>
              <p className="mt-1">
                Los plazos que dependan de este evento quedarán pendientes.
              </p>
            </div>
          </div>

          {wasDetected && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <p className="text-sm text-yellow-800">
                <strong>Nota:</strong> Este evento fue detectado automáticamente.
                Reaparecerá en el próximo análisis si está presente en el documento.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t mt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={handleDelete}
            loading={deleteMutation.isPending}
          >
            Eliminar
          </Button>
        </div>
      </div>
    </div>
  );
}
