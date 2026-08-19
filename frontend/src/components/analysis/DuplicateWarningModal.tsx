import { useMemo, useState } from "react";

import type { DuplicateAction, DuplicateDecision, DuplicateWarning } from "../../types/analysis";
import { Button } from "../Button";
import { DuplicateFileCard } from "./DuplicateFileCard";

interface DuplicateWarningModalProps {
  duplicates: DuplicateWarning[];
  onConfirm: (decisions: DuplicateDecision[]) => void;
  onCancel: () => void;
  isSubmitting?: boolean;
}

export function DuplicateWarningModal({
  duplicates,
  onConfirm,
  onCancel,
  isSubmitting = false,
}: DuplicateWarningModalProps) {
  const groupedDuplicate = useMemo(() => {
    if (duplicates.length <= 1) {
      return null;
    }

    const existingAnalysisIds = new Set(duplicates.map((duplicate) => duplicate.existing_analysis_id));
    if (existingAnalysisIds.size !== 1) {
      return null;
    }

    return {
      count: duplicates.length,
      created_at: duplicates[0]?.created_at,
      created_by: duplicates[0]?.created_by,
    };
  }, [duplicates]);

  const [actions, setActions] = useState<Record<string, DuplicateAction>>(() => {
    const seed: Record<string, DuplicateAction> = {};
    duplicates.forEach((duplicate) => {
      seed[duplicate.document_id] = "view_existing";
    });
    return seed;
  });
  const [groupAction, setGroupAction] = useState<DuplicateAction>("view_existing");

  const decisions = useMemo(
    () =>
      duplicates.map((duplicate) => ({
        document_id: duplicate.document_id,
        action: groupedDuplicate ? groupAction : (actions[duplicate.document_id] ?? "view_existing"),
      })),
    [actions, duplicates, groupAction, groupedDuplicate],
  );

  const groupedDate = groupedDuplicate
    ? new Date(groupedDuplicate.created_at).toLocaleDateString("es-AR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      })
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-2xl rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
        <h2 className="text-xl font-semibold text-gray-900">Documentos ya analizados</h2>
        <p className="mt-2 text-sm text-gray-600">
          Detectamos duplicados. Elegí si querés ver el análisis existente, analizar de nuevo o cancelar.
        </p>

        <div className="mt-4 space-y-3">
          {groupedDuplicate ? (
            <article className="rounded-md border border-amber-200 bg-amber-50 p-4">
              <h3 className="text-sm font-semibold text-gray-900">Documentos del análisis actual</h3>
              <p className="mt-1 text-xs text-amber-900">
                Estos {groupedDuplicate.count} archivos ya fueron analizados juntos el {groupedDate} por {groupedDuplicate.created_by}
              </p>
              <p className="mt-2 text-xs text-gray-700">¿Qué querés hacer con este análisis completo?</p>
              <select
                className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                value={groupAction}
                onChange={(event) => setGroupAction(event.target.value as DuplicateAction)}
              >
                <option value="view_existing">Ver análisis existente</option>
                <option value="analyze_again">Analizar de nuevo</option>
                <option value="cancel">Cancelar</option>
              </select>
            </article>
          ) : (
            duplicates.map((duplicate) => (
              <DuplicateFileCard
                key={duplicate.document_id}
                duplicate={duplicate}
                action={actions[duplicate.document_id] ?? "view_existing"}
                onActionChange={(nextAction) => {
                  setActions((current) => ({ ...current, [duplicate.document_id]: nextAction }));
                }}
              />
            ))
          )}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Cerrar
          </Button>
          <Button type="button" onClick={() => onConfirm(decisions)} loading={isSubmitting}>
            Confirmar decisiones
          </Button>
        </div>
      </div>
    </div>
  );
}
