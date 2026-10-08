import { Check } from "lucide-react";

import { cn } from "../utils/cn";

interface StepIndicatorProps {
  currentStep: number;
  totalSteps?: number;
  stepTitles?: string[];
  onStepClick?: (step: number) => void;
}

const DEFAULT_STEP_TITLES = ["Subir archivos", "Designar principal", "Confirmación"];

export function StepIndicator({
  currentStep,
  totalSteps = 3,
  stepTitles = DEFAULT_STEP_TITLES,
  onStepClick,
}: StepIndicatorProps) {
  return (
    <section aria-label="Progreso del wizard" className="flex flex-col gap-5">
      <div>
        <h1 className="font-display text-[28px] font-bold leading-[1.15] tracking-[-0.015em] text-[#003C6B]">Analizar nuevo pliego</h1>
        <p className="mt-[6px] text-sm leading-[1.5] text-[rgba(0,60,107,.68)]">
          Paso {currentStep} de {totalSteps} · {stepTitles[currentStep - 1]}
        </p>
      </div>
      <ol role="list" className="grid grid-cols-4 gap-0">
        {stepTitles.map((title, index) => {
          const step = index + 1;
          const active = step === currentStep;
          const completed = step < currentStep;
          const canNavigate = completed ? onStepClick : undefined;

          return (
            <li key={title} role="listitem" className="flex min-w-0 flex-col gap-2.5">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => canNavigate?.(step)}
                  aria-current={active ? "step" : undefined}
                  aria-disabled={!canNavigate}
                  className={cn(
                    "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 p-0 font-display text-[13px] font-bold leading-none",
                    active && "border-[#0099DB] bg-[#0099DB] text-white",
                    completed && "border-[#003C6B] bg-[#003C6B] text-white",
                    !active && !completed && "border-[rgba(0,60,107,.2)] bg-white text-[rgba(0,60,107,.55)]",
                    canNavigate ? "cursor-pointer" : "cursor-default",
                  )}
                >
                  {completed ? <Check size={14} strokeWidth={3} aria-hidden="true" /> : step}
                </button>
                <div
                  className={cn("h-0.5 flex-1 rounded-full", completed ? "bg-[#003C6B]" : "bg-[rgba(0,60,107,.12)]")}
                  aria-hidden="true"
                />
              </div>
              <span
                className={cn(
                  "text-xs tracking-[0.02em]",
                  active ? "font-bold text-[#003C6B]" : "font-medium",
                  completed ? "text-[#003C6B]" : "text-[rgba(0,60,107,.55)]",
                )}
              >
                {title}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
