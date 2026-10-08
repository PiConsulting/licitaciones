import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, RotateCcw, X } from "lucide-react";

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

export const CATEGORY_LABELS: Record<string, string> = {
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

interface OptionCardProps {
  active: boolean;
  onClick: () => void;
  title: string;
  description: string;
  children?: React.ReactNode;
}

function OptionCard({ active, onClick, title, description, children }: OptionCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex w-full flex-col gap-2.5 rounded-2xl border-[1.5px] px-4 py-3.5 text-left ${
        active ? "border-[#0099DB] bg-[#F4F9FC]" : "border-[rgba(0,60,107,.15)] bg-white"
      }`}
    >
      <span className="flex items-start gap-3">
        <span
          className={`mt-0.5 flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-full border-[1.5px] ${
            active ? "border-[#003C6B] bg-[#003C6B]" : "border-[rgba(0,60,107,.3)] bg-white"
          }`}
        >
          {active ? <span className="h-2 w-2 rounded-full bg-white" /> : null}
        </span>
        <span>
          <span className="block text-sm font-semibold text-[#003C6B]">{title}</span>
          <span className="mt-0.5 block text-[12.5px] leading-[1.5] text-[rgba(0,60,107,.6)]">{description}</span>
        </span>
      </span>
      {children ? <div className="ml-[30px] flex flex-wrap gap-1.5">{children}</div> : null}
    </button>
  );
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

  const noCategoriesSelected = type === "categories" && selectedCategories.length === 0;
  const canSubmit = !noCategoriesSelected;

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
    <div
      onClick={onCancel}
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(0,60,107,.45)] p-4"
      role="dialog"
      aria-modal="true"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-[560px] flex-col gap-5 rounded-[24px] border border-[rgba(0,60,107,.12)] bg-white p-7 shadow-[0_24px_60px_rgba(0,60,107,.28)]"
        style={{ maxHeight: "calc(100vh - 48px)", overflowY: "auto" }}
        data-testid="reanalyze-modal"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-[38px] w-[38px] flex-shrink-0 items-center justify-center rounded-xl bg-[rgba(0,153,219,.12)] text-[#0099DB]">
              <RotateCcw className="h-[18px] w-[18px]" />
            </span>
            <div>
              <h2 className="font-display text-[19px] font-bold text-[#003C6B]">Reanalizar</h2>
              <p className="mt-0.5 text-[12.5px] text-[rgba(0,60,107,.6)]">
                Cada reanálisis crea una nueva versión del análisis
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Cerrar"
            className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-full border-0 bg-transparent text-[rgba(0,60,107,.45)] hover:bg-[#F4F9FC] hover:text-[#003C6B]"
          >
            <X className="h-[15px] w-[15px]" />
          </button>
        </div>

        <fieldset className="flex flex-col gap-2.5 border-0 p-0" aria-label="Alcance del reanálisis">
          <OptionCard
            active={type === "all"}
            onClick={() => setType("all")}
            title="Reanalizar todo"
            description="Vuelve a extraer todas las categorías del pliego, fase 1 y fase 2."
          />

          <OptionCard
            active={type === "phase1"}
            onClick={() => setType("phase1")}
            title="Fase 1"
            description="Objeto, criterios de preview, requisitos, plazos, garantías y riesgos."
          >
            {type === "phase1" ? (
              <div className="flex flex-wrap gap-1.5" data-testid="reanalyze-phase1-categories">
                {PHASE1_CATEGORIES.map((categoryId) => (
                  <span
                    key={categoryId}
                    className="inline-flex rounded-full bg-[rgba(0,60,107,.06)] px-2.5 py-[3px] text-[11px] font-semibold text-[rgba(0,60,107,.68)]"
                  >
                    {labelFor(categoryId)}
                  </span>
                ))}
              </div>
            ) : null}
          </OptionCard>

          <OptionCard
            active={type === "phase2"}
            onClick={() => setType("phase2")}
            title="Fase 2"
            description="Causales de rechazo, anexos, criterios de evaluación y eventos temporales."
          >
            {type === "phase2" ? (
              <div className="flex flex-wrap gap-1.5" data-testid="reanalyze-phase2-categories">
                {PHASE2_CATEGORIES.map((categoryId) => (
                  <span
                    key={categoryId}
                    className="inline-flex rounded-full bg-[rgba(0,60,107,.06)] px-2.5 py-[3px] text-[11px] font-semibold text-[rgba(0,60,107,.68)]"
                  >
                    {labelFor(categoryId)}
                  </span>
                ))}
              </div>
            ) : null}
          </OptionCard>

          <OptionCard
            active={type === "categories"}
            onClick={() => setType("categories")}
            title="Seleccionar categorías"
            description="Elegí puntualmente qué categorías volver a analizar."
          >
            {type === "categories" ? (
              <>
                <div className="flex flex-wrap gap-1.5" data-testid="reanalyze-custom-categories">
                  {allCategories.map((categoryId) => {
                    const checked = selectedCategories.includes(categoryId);
                    return (
                      <span
                        key={categoryId}
                        role="checkbox"
                        aria-checked={checked}
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleCategory(categoryId);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            toggleCategory(categoryId);
                          }
                        }}
                        className={`inline-flex cursor-pointer select-none items-center gap-1.5 rounded-full border-[1.5px] px-3 py-[5px] text-xs font-semibold ${
                          checked
                            ? "border-[#003C6B] bg-[#003C6B] text-white"
                            : "border-[rgba(0,60,107,.2)] bg-white text-[#003C6B]"
                        }`}
                      >
                        {checked ? <Check className="h-[11px] w-[11px]" strokeWidth={3} /> : null}
                        {labelFor(categoryId)}
                      </span>
                    );
                  })}
                </div>
                {noCategoriesSelected ? (
                  <p className="text-xs text-[#DC2626]">Elegí al menos una categoría</p>
                ) : null}
              </>
            ) : null}
          </OptionCard>
        </fieldset>

        <div className="flex justify-end gap-2.5 border-t border-[rgba(0,60,107,.12)] pt-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="inline-flex h-[38px] items-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB] disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={!canSubmit || isSubmitting}
            className="inline-flex h-[38px] items-center gap-[7px] rounded-full border-0 bg-[#003C6B] px-5 text-[13px] font-semibold text-white hover:bg-[#0099DB] disabled:cursor-not-allowed disabled:bg-[rgba(0,60,107,.3)] disabled:hover:bg-[rgba(0,60,107,.3)]"
          >
            {isSubmitting ? <Loader2 className="h-[13px] w-[13px] animate-spin" /> : null}
            Confirmar reanálisis
          </button>
        </div>
      </div>
    </div>
  );
}
