import type { BusinessStatus } from "../../../types/businessStatus";
import { formatIsoDate } from "../utils/businessStatus";

interface BusinessStatusStepperProps {
  status: BusinessStatus;
  presentedAt?: string | null;
}

interface StepView {
  label: string;
  sub: string;
  mark: string;
  dotBg: string;
  dotBorder: string;
  dotFg: string;
  labelFg: string;
  current: boolean;
  leftLine: string;
  rightLine: string;
}

const NAVY = "#003C6B";
const MUTED_LINE = "rgba(0,60,107,.12)";

const STATUS_RANK: Record<BusinessStatus, number> = {
  en_analisis: 1,
  pendiente_decision: 2,
  no_aprobada: 2,
  en_revision: 3,
  presentada: 4,
  ganada: 5,
  perdida: 5,
};

function buildSteps(status: BusinessStatus, presentedAt?: string | null): StepView[] {
  const rank = STATUS_RANK[status];
  const dead = status === "no_aprobada";
  const finished = status === "ganada" || status === "perdida";

  const definitions: [string, string][] = [
    ["Análisis Fase 1", status === "en_analisis" ? "En curso" : "Completado"],
    [
      dead ? "No aprobada" : "Decisión",
      status === "en_analisis" ? "—" : status === "pendiente_decision" ? "Pendiente" : dead ? "No sigue" : "Aprobada",
    ],
    ["En revisión", status === "en_revision" ? "Fase 2 lista" : rank > 3 ? "Revisada" : "—"],
    ["Presentada", rank >= 4 ? formatIsoDate(presentedAt) : "—"],
    ["Resultado", status === "ganada" ? "Ganada" : status === "perdida" ? "Perdida" : "—"],
  ];

  return definitions.map(([label, sub], index) => {
    const position = index + 1;
    const done = position < rank || (finished && position === 5);
    const active = position === rank && !finished && !dead;
    const terminal = dead && position === 2;
    const resultColor = status === "ganada" ? "#1FC9A8" : "rgba(0,60,107,.55)";

    let dotBg = "#fff";
    let dotBorder = "rgba(0,60,107,.2)";
    let dotFg = "rgba(0,60,107,.45)";
    let mark = String(position);
    let labelFg = "rgba(0,60,107,.55)";

    if (done) {
      dotBg = position === 5 ? resultColor : NAVY;
      dotBorder = dotBg;
      dotFg = position === 5 && status === "ganada" ? "#063D33" : "#fff";
      mark = position === 5 ? (status === "ganada" ? "✓" : "✕") : "✓";
      labelFg = NAVY;
    }
    if (active) {
      dotBorder = "#2F4EF8";
      dotFg = "#2F4EF8";
      labelFg = NAVY;
    }
    if (terminal) {
      dotBg = "rgba(0,60,107,.55)";
      dotBorder = dotBg;
      dotFg = "#fff";
      mark = "✕";
      labelFg = NAVY;
    }

    const leftReached = position > 1 && position - 1 < rank;
    const rightReached = position < rank;

    return {
      label,
      sub,
      mark,
      dotBg,
      dotBorder,
      dotFg,
      labelFg,
      current: active,
      leftLine: position === 1 ? "transparent" : leftReached || finished ? NAVY : MUTED_LINE,
      rightLine: position === 5 ? "transparent" : rightReached || finished ? NAVY : MUTED_LINE,
    };
  });
}

export function BusinessStatusStepper({ status, presentedAt }: BusinessStatusStepperProps) {
  const steps = buildSteps(status, presentedAt);

  return (
    <section
      aria-label="Recorrido de la licitación"
      className="rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-4 py-5"
      data-testid="business-status-stepper"
    >
      <ol className="flex">
        {steps.map((step) => (
          <li
            key={step.label}
            aria-current={step.current ? "step" : undefined}
            className="relative flex min-w-0 flex-1 flex-col items-center px-1 text-center"
          >
            <div className="absolute left-0 top-[14px] h-0.5 w-1/2" style={{ background: step.leftLine }} />
            <div className="absolute right-0 top-[14px] h-0.5 w-1/2" style={{ background: step.rightLine }} />
            <span
              className="relative z-10 flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-bold"
              style={{ background: step.dotBg, borderColor: step.dotBorder, color: step.dotFg }}
            >
              {step.mark}
            </span>
            <div className="mt-2 min-w-0">
              <div className="text-[12.5px] font-semibold" style={{ color: step.labelFg }}>
                {step.label}
              </div>
              <div className="mt-0.5 text-[11.5px] text-[rgba(0,60,107,.55)]">{step.sub}</div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
