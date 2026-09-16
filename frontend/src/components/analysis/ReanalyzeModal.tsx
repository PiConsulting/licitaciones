import { useEffect, useMemo, useState } from "react";

import { Button } from "../Button";
import type { ReanalyzeRequest, ReanalyzeType } from "../../types/analysis";

interface ReanalyzeModalProps {
  open: boolean;
  isSubmitting?: boolean;
  onCancel: () => void;
  onConfirm: (payload: ReanalyzeRequest) => Promise<void>;
}

const PHASE1_CATEGORIES = [
  "preview_criterios",
  "objeto_alcance",
  "identificacion_procedimiento",
  "requisitos_admisibilidad",
  "plazos_clave",
  "garantias",
  "riesgos",
];

const PHASE2_CATEGORIES = [
  "causales_rechazo",
  "anexos_obligatorios",
  "criterios_evaluacion",
  "eventos_temporales",
  "plazos_relativos",
];

const CATEGORY_LABELS: Record<string, string> = {
  preview_criterios: "Preview: criterios comerciales",
  objeto_alcance: "Objeto y alcance",
  identificacion_procedimiento: "Identificación del procedimiento",
  requisitos_admisibilidad: "Requisitos de admisibilidad",
  plazos_clave: "Plazos clave",
  garantias: "Garantías",
  riesgos: "Riesgos",
  causales_rechazo: "Causales de rechazo",
  anexos_obligatorios: "Anexos obligatorios",
  criterios_evaluacion: "Criterios de evaluación",
  eventos_temporales: "Eventos temporales",
  plazos_relativos: "Plazos relativos",
};

function labelFor(categoryId: string): string {
  return CATEGORY_LABELS[categoryId] ?? categoryId;
}

export function ReanalyzeModal({ open, isSubmitting = false, onCancel, onConfirm }: ReanalyzeModalProps) {
  const [type, setType] = useState<ReanalyzeType>("all");
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      return;
    }
    setType("all");
    setSelectedCategories([]);
  }, [open]);

  const allCategories = useMemo(() => {
    return Array.from(new Set([...PHASE1_CATEGORIES, ...PHASE2_CATEGORIES]));
  }, []);

  if (!open) {
    return null;
  }

  const canSubmit = type !== "categories" || selectedCategories.length > 0;

  const toggleCategory = (categoryId: string) => {
    setSelectedCategories((current) =>
      current.includes(categoryId)
        ? current.filter((value) => value !== categoryId)
        : [...current, categoryId],
    );
  };

  const handleConfirm = async () => {
    if (!canSubmit || isSubmitting) {
      return;
    }
    await onConfirm({
      reanalysis_type: type,
      categories: type === "categories" ? selectedCategories : [],
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-2xl rounded-lg border border-gray-200 bg-white p-6 shadow-xl" data-testid="reanalyze-modal">
        <h2 className="text-xl font-semibold text-gray-900">Reanalizar</h2>
        <p className="mt-2 text-sm text-gray-600">
          Cada reanálisis crea una nueva versión. Elegí el alcance que querés recalcular.
        </p>

        <fieldset className="mt-5 space-y-3" aria-label="Opciones de reanálisis">
          <label className="flex items-start gap-3">
            <input
              type="radio"
              name="reanalyze-type"
              checked={type === "all"}
              onChange={() => setType("all")}
            />
            <span className="text-sm text-gray-800">Reanalizar todo</span>
          </label>

          <label className="flex items-start gap-3">
            <input
              type="radio"
              name="reanalyze-type"
              checked={type === "phase1"}
              onChange={() => setType("phase1")}
            />
            <span className="text-sm text-gray-800">Fase 1</span>
          </label>
          {type === "phase1" ? (
            <ul className="ml-7 list-disc text-xs text-gray-600" data-testid="reanalyze-phase1-categories">
              {PHASE1_CATEGORIES.map((categoryId) => (
                <li key={categoryId}>{labelFor(categoryId)}</li>
              ))}
            </ul>
          ) : null}

          <label className="flex items-start gap-3">
            <input
              type="radio"
              name="reanalyze-type"
              checked={type === "phase2"}
              onChange={() => setType("phase2")}
            />
            <span className="text-sm text-gray-800">Fase 2</span>
          </label>
          {type === "phase2" ? (
            <ul className="ml-7 list-disc text-xs text-gray-600" data-testid="reanalyze-phase2-categories">
              {PHASE2_CATEGORIES.map((categoryId) => (
                <li key={categoryId}>{labelFor(categoryId)}</li>
              ))}
            </ul>
          ) : null}

          <label className="flex items-start gap-3">
            <input
              type="radio"
              name="reanalyze-type"
              checked={type === "categories"}
              onChange={() => setType("categories")}
            />
            <span className="text-sm text-gray-800">Seleccionar categorías</span>
          </label>
          {type === "categories" ? (
            <div className="ml-7 grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="reanalyze-custom-categories">
              {allCategories.map((categoryId) => (
                <label key={categoryId} className="flex items-center gap-2 text-xs text-gray-700">
                  <input
                    type="checkbox"
                    checked={selectedCategories.includes(categoryId)}
                    onChange={() => toggleCategory(categoryId)}
                  />
                  <span>{labelFor(categoryId)}</span>
                </label>
              ))}
            </div>
          ) : null}
        </fieldset>

        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button type="button" onClick={() => void handleConfirm()} loading={isSubmitting} disabled={!canSubmit}>
            Confirmar reanálisis
          </Button>
        </div>
      </div>
    </div>
  );
}
