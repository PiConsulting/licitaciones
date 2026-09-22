import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Button } from "../Button";
import { Input } from "../Input";
import { updateEvent, recalculateDependentDates } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import type { EventResponse } from "../../types/timeline";

interface EditDateModalProps {
  event: EventResponse;
  open: boolean;
  onClose: () => void;
}

export function EditDateModal({ event, open, onClose }: EditDateModalProps) {
  const [date, setDate] = useState(event.event_date || "");
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const wasCalculated = event.date_source === "calculated";

  const updateMutation = useMutation({
    mutationFn: async (newDate: string) => {
      await updateEvent(event.analysis_id, event.event_id, {
        event_date: newDate,
        date_source: "user_input",
      });

      try {
        const stats = await recalculateDependentDates(event.analysis_id, event.event_id);
        return { stats, recalcFailed: false };
      } catch (recalcError) {
        console.error('Recalculation failed after date update:', recalcError);
        return { stats: { events_updated: 0, errors: [] }, recalcFailed: true };
      }
    },
    onSuccess: ({ stats, recalcFailed }) => {
      queryClient.invalidateQueries({ queryKey: ["timeline", event.analysis_id] });
      queryClient.invalidateQueries({ queryKey: ["timeline-deadlines", event.analysis_id] });

      if (recalcFailed) {
        addToast("error", "Fecha actualizada pero el recálculo de dependencias falló. Intenta recargar la página.");
        onClose();
        return;
      }

      if (stats.errors && stats.errors.length > 0) {
        addToast(
          "error",
          `Fecha actualizada pero ${stats.errors.length} evento(s) no se pudieron recalcular. Revisa la timeline.`
        );
      } else {
        const message =
          stats.events_updated > 0
            ? `Fecha actualizada. Se recalcularon ${stats.events_updated} eventos dependientes`
            : "Fecha actualizada correctamente";
        addToast("success", message);
      }

      onClose();
    },
    onError: (error: Error) => {
      addToast("error", error.message || "Error al actualizar fecha");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!date) {
      addToast("error", "Debe seleccionar una fecha");
      return;
    }
    updateMutation.mutate(date);
  };

  const handleCancel = () => {
    onClose();
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">
          Editar fecha de &quot;{event.name}&quot;
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4" noValidate>
          <Input
            label="Fecha"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />

          {wasCalculated && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-yellow-800">
                <p className="font-medium">Esta fecha se calculó automáticamente</p>
                <p className="mt-1">
                  Al modificarla manualmente, futuros recálculos no la sobrescribirán. La fecha
                  quedará fijada como ingresada por el usuario.
                </p>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button type="button" variant="secondary" onClick={handleCancel}>
              Cancelar
            </Button>
            <Button type="submit" variant="primary" loading={updateMutation.isPending}>
              Actualizar
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
