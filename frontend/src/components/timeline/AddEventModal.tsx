import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../Button";
import { Input } from "../Input";
import { createEvent } from "../../api/timeline";
import { EventResponse } from "../../types/timeline";
import { useToast } from "../ToastContainer";

interface AddEventModalProps {
  analysisId: string;
  open: boolean;
  onClose: () => void;
}

export function AddEventModal({ analysisId, open, onClose }: AddEventModalProps) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const queryClient = useQueryClient();
  const { addToast } = useToast();

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      event_date: string | null;
      date_source: "user_input" | "pending";
      status: "confirmed";
      source_fragment?: string;
    }) => createEvent(analysisId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["timeline", analysisId] });
      addToast("success", "Evento agregado correctamente"); // F4 fix
      onClose();
      resetForm();
    },
    onError: (error: Error) => {
      // Toast error handled by mutation
      console.error("Error creating event:", error);
    },
  });

  const resetForm = () => {
    setName("");
    setDate("");
    setNotes("");
    setErrors({});
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Validación
    const newErrors: Record<string, string> = {};
    if (!name.trim()) {
      newErrors.name = "El nombre del evento es obligatorio";
    }

    // F8 fix: Validar longitud de source_fragment
    if (notes && notes.length > 500) {
      newErrors.notes = "Las observaciones no pueden exceder 500 caracteres";
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    createMutation.mutate({
      name: name.trim(),
      event_date: date || null,
      date_source: date ? "user_input" : "pending",
      status: "confirmed",
      source_fragment: notes.trim() || undefined,
    });
  };

  const handleCancel = () => {
    resetForm();
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
        <h2 className="text-xl font-semibold text-gray-900">Agregar evento</h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4" noValidate>
          <Input
            label="Nombre del evento"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (errors.name) {
                setErrors((prev) => ({ ...prev, name: "" }));
              }
            }}
            error={errors.name}
            placeholder="ej: Adjudicación, Entrega de equipamiento..."
          />

          <Input
            label="Fecha (opcional)"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />

          <div>
            <label htmlFor="notes" className="block text-sm font-medium text-gray-700 mb-1">
              Observación (opcional)
            </label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              rows={3}
              placeholder="Notas adicionales sobre este evento..."
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button type="button" variant="secondary" onClick={handleCancel}>
              Cancelar
            </Button>
            <Button type="submit" variant="primary" loading={createMutation.isPending}>
              Guardar
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
