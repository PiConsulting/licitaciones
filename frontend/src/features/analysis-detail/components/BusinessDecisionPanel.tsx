import { Check } from "lucide-react";
import { useState } from "react";


interface BusinessDecisionPanelProps {
  loading: boolean;
  onApprove: () => Promise<void> | void;
  onReject: (note: string) => Promise<void> | void;
}

export function BusinessDecisionPanel({ loading, onApprove, onReject }: BusinessDecisionPanelProps) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");

  const confirmReject = async () => {
    await onReject(note.trim());
    setRejecting(false);
    setNote("");
  };

  const cancelReject = () => {
    setRejecting(false);
    setNote("");
  };

  return (
    <section
      className="flex flex-col gap-4 rounded-2xl bg-[#003C6B] px-6 py-5 text-white"
      data-testid="business-decision-panel"
    >
      <div>
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#7FF3DE]">
          Decisión · Fase 1 completada
        </span>
        <h3 className="mt-1.5 font-display text-[18px] font-bold leading-[1.2]">
          ¿Aprobamos esta licitación para el análisis completo?
        </h3>
        <p className="mt-1.5 text-[13px] text-white/75">
          Si la aprobás, arranca el análisis de Fase 2 y la licitación pasa directamente a{" "}
          <strong className="font-semibold text-white">En revisión</strong>. Si no, queda como No aprobada y podés
          reabrirla cuando quieras.
        </p>
      </div>

      {rejecting ? (
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="business-reject-note"
            className="text-[11px] font-bold uppercase tracking-[0.14em] text-white/75"
          >
            Motivo (opcional)
          </label>
          <textarea
            id="business-reject-note"
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Ej: monto fuera de alcance, no tenemos el equipo técnico..."
            className="w-full resize-y rounded-2xl border-[1.5px] border-white/30 bg-white/[.08] px-4 py-3 text-sm text-white placeholder:text-white/50 focus-visible:border-white focus-visible:outline-none"
          />
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2.5">
        {rejecting ? (
          <>
            <button
              type="button"
              onClick={() => void confirmReject()}
              disabled={loading}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-[#003C6B] transition-colors hover:bg-[#7FF3DE] disabled:opacity-60"
            >
              Confirmar: no aprobar
            </button>
            <button
              type="button"
              onClick={cancelReject}
              disabled={loading}
              className="inline-flex h-11 items-center rounded-full border-2 border-white/40 bg-transparent px-5 text-sm font-semibold text-white transition-colors hover:border-white disabled:opacity-60"
            >
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void onApprove()}
              disabled={loading}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-white px-5 text-sm font-semibold text-[#003C6B] transition-colors hover:bg-[#7FF3DE] disabled:opacity-60"
            >
              <Check className="h-4 w-4" aria-hidden="true" />
              Aprobar y analizar Fase 2
            </button>
            <button
              type="button"
              onClick={() => setRejecting(true)}
              disabled={loading}
              className="inline-flex h-11 items-center rounded-full border-2 border-white/40 bg-transparent px-5 text-sm font-semibold text-white transition-colors hover:border-white disabled:opacity-60"
            >
              No aprobar
            </button>
          </>
        )}
      </div>
    </section>
  );
}
