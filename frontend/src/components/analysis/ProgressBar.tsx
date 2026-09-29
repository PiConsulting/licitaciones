import { useEffect, useRef, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

const STAGE_DISPLAY_NAMES: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Preparando para análisis",
  analyzing: "Analizando",
  consolidating: "Consolidando",
  completed: "Analizado",
};

const CATCH_UP_INTERVAL_MS = 90;
const DONE_COUNT_INTERVAL_MS = 2500;

interface ProgressBarProps {
  stage: string;
  progress: number;
  isProcessing: boolean;
  stageProgress?: string | null;
  metaSlot?: ReactNode;
}

function parseCountedProgress(text: string): { prefix: string; done: number; total: number } | null {
  const match = text.match(/^(.+?)\s*\((\d+)\s+de\s+(\d+)\)$/);
  if (!match) return null;
  return { prefix: match[1].trim(), done: parseInt(match[2]), total: parseInt(match[3]) };
}

export function ProgressBar({ stage, progress, isProcessing, stageProgress, metaSlot }: ProgressBarProps) {
  const [displayProgress, setDisplayProgress] = useState(0);
  const [simulatedDone, setSimulatedDone] = useState(0);
  const targetRef = useRef(0);
  const catchUpIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cada corrida nueva (análisis o reanálisis, sea cual sea la fase o categoría elegida) arranca
  // en cola: reiniciamos la animación en 0 para que nunca se vea "saltar" a un valor alto.
  useEffect(() => {
    if (stage === "queued") {
      targetRef.current = 0;
      setDisplayProgress(0);
    }
  }, [stage]);

  // El progreso real que manda el backend define el objetivo. Nunca retrocede, salvo que sea
  // una corrida nueva (queued), donde se reinicia arriba.
  useEffect(() => {
    targetRef.current = stage === "queued" ? 0 : Math.max(targetRef.current, progress);
  }, [progress, stage]);

  // Anima el valor mostrado acercándolo de a poco al objetivo real en vez de saltar directo:
  // esto simula el avance mientras corren nodos en paralelo (el backend solo reporta saltos
  // grandes entre etapas) y, cuando el progreso real llega más seguido (proceso de una sola
  // categoría), simplemente lo alcanza más rápido.
  useEffect(() => {
    if (catchUpIntervalRef.current) clearInterval(catchUpIntervalRef.current);
    if (!isProcessing) {
      setDisplayProgress(targetRef.current);
      return;
    }
    catchUpIntervalRef.current = setInterval(() => {
      setDisplayProgress((prev) => {
        const target = targetRef.current;
        if (prev >= target) return prev;
        const step = Math.max(1, Math.ceil((target - prev) / 8));
        return Math.min(target, prev + step);
      });
    }, CATCH_UP_INTERVAL_MS);

    return () => {
      if (catchUpIntervalRef.current) clearInterval(catchUpIntervalRef.current);
    };
  }, [isProcessing, progress, stage]);

  // Cuenta simulada de "(N de M)" para cuando varias categorías se analizan en paralelo y el
  // backend no puede reportar avances parciales reales. Con una sola categoría (total <= 1) no
  // hay nada que simular: se muestra directamente el valor real que llega del backend.
  useEffect(() => {
    if (doneIntervalRef.current) clearInterval(doneIntervalRef.current);
    setSimulatedDone(0);
    if (stage !== "analyzing" || !isProcessing) return;

    const parsed = stageProgress ? parseCountedProgress(stageProgress) : null;
    if (!parsed || parsed.total <= 1) return;

    const { total } = parsed;
    doneIntervalRef.current = setInterval(() => {
      setSimulatedDone((prev) => (prev >= total - 1 ? prev : prev + 1));
    }, DONE_COUNT_INTERVAL_MS);

    return () => {
      if (doneIntervalRef.current) clearInterval(doneIntervalRef.current);
    };
  }, [stage, isProcessing, stageProgress]);

  const stageName = STAGE_DISPLAY_NAMES[stage] || stage;
  const clampedProgress = Math.max(0, Math.min(100, Math.round(displayProgress)));

  let displayStageProgress = stageProgress;
  if (stageProgress && stage === "analyzing") {
    const parsed = parseCountedProgress(stageProgress);
    if (parsed && parsed.total > 1) {
      const displayDone = Math.max(parsed.done, simulatedDone);
      displayStageProgress = `${parsed.prefix} (${displayDone} de ${parsed.total})`;
    }
  }

  return (
    <div className="flex flex-col gap-[18px] rounded-2xl border border-[rgba(0,60,107,.12)] bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <span className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full bg-[#F4F9FC] text-[#0099DB]">
            <Loader2 className={`h-5 w-5 ${isProcessing ? "animate-spin" : ""}`} strokeWidth={2.5} />
          </span>
          <div>
            <h2 className="font-display text-[22px] font-bold leading-[1.15] text-[#003C6B]">{stageName}…</h2>
            <p className="mt-1 text-sm text-[rgba(0,60,107,.68)]">
              {displayStageProgress || "Procesando en segundo plano"}
            </p>
          </div>
        </div>
        <span className="font-display text-[36px] font-bold leading-none tracking-[-0.03em] text-[#003C6B]">
          {clampedProgress}%
        </span>
      </div>

      {metaSlot}

      <div className="h-2 overflow-hidden rounded-full bg-[rgba(0,60,107,.1)]">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${clampedProgress}%`, background: "linear-gradient(90deg,#0099DB,#7FF3DE)" }}
        />
      </div>
    </div>
  );
}
