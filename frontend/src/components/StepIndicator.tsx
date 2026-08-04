import { cn } from "../utils/cn";

interface StepIndicatorProps {
  currentStep: number;
  totalSteps?: number;
  stepTitles?: string[];
}

const DEFAULT_STEP_TITLES = ["Subir archivos", "Designar principal", "Confirmación"];

export function StepIndicator({ currentStep, totalSteps = 3, stepTitles = DEFAULT_STEP_TITLES }: StepIndicatorProps) {
  return (
    <section aria-label="Progreso del wizard" className="space-y-4">
      <h1 className="text-2xl font-semibold text-gray-900">Analizar nuevo pliego</h1>
      <p className="text-sm font-medium text-gray-700">
        Paso {currentStep} de {totalSteps}: {stepTitles[currentStep - 1]}
      </p>
      <div className={`grid gap-3 ${stepTitles.length === 4 ? "grid-cols-2 md:grid-cols-4" : "grid-cols-3"}`} role="list">
        {stepTitles.map((title, index) => {
          const step = index + 1;
          const active = step === currentStep;
          const completed = step < currentStep;

          return (
            <div
              key={title}
              role="listitem"
              className={cn(
                "rounded-md border px-3 py-2 text-sm font-medium",
                active && "border-primary bg-primary-light text-primary",
                completed && "border-success bg-success-light text-green-700",
                !active && !completed && "border-gray-200 bg-white text-gray-600",
              )}
            >
              {step}. {title}
            </div>
          );
        })}
      </div>
    </section>
  );
}
