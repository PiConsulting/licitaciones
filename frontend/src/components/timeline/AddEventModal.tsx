import { useState } from "react";
import { CalendarPlus, Loader2, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DatePicker } from "../DatePicker";
import { createEvent } from "../../api/timeline";
import { useToast } from "../ToastContainer";
import { useTimelineMarkedDates } from "./markedDates";

interface AddEventModalProps {
  analysisId: string;
  open: boolean;
  onClose: () => void;
}

const MAX_NOTES_LENGTH = 500;

export function AddEventModal({ analysisId, open, onClose }: AddEventModalProps) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const markedDates = useTimelineMarkedDates(analysisId);

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
      addToast("success", "Evento agregado correctamente");
      onClose();
      resetForm();
    },
    onError: (error: Error) => {
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

    const newErrors: Record<string, string> = {};
    if (!name.trim()) {
      newErrors.name = "El nombre del evento es obligatorio";
    }

    if (notes.length > MAX_NOTES_LENGTH) {
      newErrors.notes = `Las observaciones no pueden exceder ${MAX_NOTES_LENGTH} caracteres`;
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(0,60,107,.45)] p-4"
      role="dialog"
      aria-modal="true"
      onClick={handleCancel}
    >
      <div
        className="w-full max-w-[440px] rounded-3xl border border-[rgba(0,60,107,.12)] bg-white p-7 shadow-[0_24px_60px_rgba(0,60,107,.28)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-[38px] w-[38px] flex-shrink-0 items-center justify-center rounded-xl bg-[rgba(0,153,219,.12)] text-[#0099DB]">
              <CalendarPlus className="h-[18px] w-[18px]" />
            </span>
            <div>
              <h2 className="font-display text-[19px] font-bold text-[#003C6B]">Agregar evento</h2>
              <p className="mt-0.5 text-[12.5px] text-[rgba(0,60,107,.6)]">
                Se suma a la línea de tiempo de este análisis
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleCancel}
            aria-label="Cerrar"
            className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-full border-0 bg-transparent text-[rgba(0,60,107,.45)] hover:bg-[#F4F9FC] hover:text-[#003C6B]"
          >
            <X className="h-[15px] w-[15px]" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="ae-name" className="mb-1.5 block text-[13px] font-semibold text-[#003C6B]">
              Nombre del evento
            </label>
            <input
              id="ae-name"
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (errors.name) {
                  setErrors((prev) => ({ ...prev, name: "" }));
                }
              }}
              placeholder="ej: Adjudicación, Entrega de equipamiento..."
              aria-invalid={Boolean(errors.name)}
              className={`h-[42px] w-full rounded-xl border-[1.5px] bg-white px-3.5 text-sm text-[#003C6B] focus-visible:border-[#0099DB] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0099DB] ${
                errors.name ? "border-[#DC2626]" : "border-[rgba(0,60,107,.2)]"
              }`}
            />
            {errors.name ? <p className="mt-[5px] text-xs text-[#DC2626]">{errors.name}</p> : null}
          </div>

          <div>
            <label htmlFor="ae-date" className="mb-1.5 block text-[13px] font-semibold text-[#003C6B]">
              Fecha <span className="font-medium text-[rgba(0,60,107,.5)]">(opcional)</span>
            </label>
            <DatePicker
              id="ae-date"
              value={date || null}
              onChange={setDate}
              markedDates={markedDates}
              placeholder="Elegir fecha"
              aria-label="Fecha del evento"
            />
            <p className="mt-[5px] text-xs text-[rgba(0,60,107,.55)]">
              Si no la cargás ahora, el evento queda como pendiente hasta que se defina.
            </p>
          </div>

          <div>
            <div className="mb-1.5 flex items-baseline justify-between">
              <label htmlFor="ae-notes" className="block text-[13px] font-semibold text-[#003C6B]">
                Observación <span className="font-medium text-[rgba(0,60,107,.5)]">(opcional)</span>
              </label>
              <span className="text-[11px] text-[rgba(0,60,107,.45)]">
                {notes.length}/{MAX_NOTES_LENGTH}
              </span>
            </div>
            <textarea
              id="ae-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Notas adicionales sobre este evento..."
              aria-invalid={Boolean(errors.notes)}
              className={`w-full resize-y rounded-xl border-[1.5px] bg-white px-3.5 py-2.5 text-sm text-[#003C6B] focus-visible:border-[#0099DB] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0099DB] ${
                errors.notes ? "border-[#DC2626]" : "border-[rgba(0,60,107,.2)]"
              }`}
            />
            {errors.notes ? <p className="mt-[5px] text-xs text-[#DC2626]">{errors.notes}</p> : null}
          </div>

          <div className="flex justify-end gap-2.5 border-t border-[rgba(0,60,107,.12)] pt-4">
            <button
              type="button"
              onClick={handleCancel}
              className="inline-flex h-[38px] items-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB]"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="inline-flex h-[38px] items-center gap-[7px] rounded-full border-0 bg-[#003C6B] px-5 text-[13px] font-semibold text-white hover:bg-[#0099DB] disabled:opacity-60"
            >
              {createMutation.isPending ? <Loader2 className="h-[13px] w-[13px] animate-spin" /> : null}
              Guardar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
