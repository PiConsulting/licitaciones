import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../Button";
import { Input } from "../Input";
import { updateEvent, recalculateDependentDates } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import type { EventResponse } from "../../types/timeline";

interface AddDateModalProps {
  event: EventResponse;
  open: boolean;
  onClose: () => void;
}

export function AddDateModal({ event, open, onClose }: AddDateModalProps) {
  const [date, setDate] = useState("");
  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const updateMutation = useMutation({
    mutationFn: async (newDate: string) => {
      // 1. Actualizar evento
      await updateEvent(event.analysis_id, event.event_id, {
        event_date: newDate,
        date_source: "user_input",
      });

      // 2. Recalcular dependencias (F2 fix: separate try/catch)
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

      // F2 fix: Show error if recalculation failed
      if (recalcFailed) {
        addToast("error", "Fecha agregada pero el recálculo de dependencias falló. Intenta recargar la página.");
        onClose();
        setDate("");
        return;
      }

      // F7 fix: Check for partial errors
      if (stats.errors && stats.errors.length > 0) {
        addToast(
          "error",
          `Fecha agregada pero ${stats.errors.length} evento(s) no se pudieron recalcular. Revisa la timeline.`
        );
      } else {
        const message =
          stats.events_updated > 0
            ? `Fecha agregada. Se calcularon ${stats.events_updated} eventos dependientes`
            : "Fecha agregada correctamente";
        addToast("success", message);
      }

      onClose();
      setDate("");
    },
    onError: (error: Error) => {
      addToast("error", error.message || "Error al agregar fecha");
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
    setDate("");
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
          Agregar fecha a &quot;{event.name}&quot;
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4" noValidate>
          <Input
            label="Fecha"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />

          <div className="rounded-md bg-blue-50 border border-blue-200 p-3">
            <p className="text-sm text-blue-800">
              Al agregar la fecha, se calcularán automáticamente los eventos que dependen de este
              hito.
            </p>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button type="button" variant="secondary" onClick={handleCancel}>
              Cancelar
            </Button>
            <Button type="submit" variant="primary" loading={updateMutation.isPending}>
              Guardar
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
