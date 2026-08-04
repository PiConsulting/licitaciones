import { useMemo, useState } from "react";

import type { DuplicateAction, DuplicateDecision, DuplicateWarning } from "../../types/analysis";
import { Button } from "../Button";
import { DuplicateFileCard } from "./DuplicateFileCard";

interface DuplicateWarningModalProps {
  duplicates: DuplicateWarning[];
  onConfirm: (decisions: DuplicateDecision[]) => void;
  onCancel: () => void;
}

export function DuplicateWarningModal({ duplicates, onConfirm, onCancel }: DuplicateWarningModalProps) {
  const [actions, setActions] = useState<Record<string, DuplicateAction>>(() => {
    const seed: Record<string, DuplicateAction> = {};
    duplicates.forEach((duplicate) => {
      seed[duplicate.document_id] = "view_existing";
    });
    return seed;
  });

  const decisions = useMemo(
    () =>
      duplicates.map((duplicate) => ({
        document_id: duplicate.document_id,
        action: actions[duplicate.document_id] ?? "view_existing",
      })),
    [actions, duplicates],
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-2xl rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">Documentos ya analizados</h2>
        <p className="mt-2 text-sm text-gray-600">
          Detectamos duplicados. Elegí una acción por archivo: Ver análisis existente, Analizar de nuevo o Cancelar.
        </p>

        <div className="mt-4 space-y-3">
          {duplicates.map((duplicate) => (
            <DuplicateFileCard
              key={duplicate.document_id}
              duplicate={duplicate}
              action={actions[duplicate.document_id] ?? "view_existing"}
              onActionChange={(nextAction) => {
                setActions((current) => ({ ...current, [duplicate.document_id]: nextAction }));
              }}
            />
          ))}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cerrar
          </Button>
          <Button type="button" onClick={() => onConfirm(decisions)}>
            Confirmar decisiones
          </Button>
        </div>
      </div>
    </div>
  );
}
