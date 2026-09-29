import { useEffect, useRef, useState } from "react";

interface ProgressBarProps {
  stage: string;
  progress: number;
  stageProgress?: string | null;
}

const STAGE_LABELS: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Preparando para análisis",
  analyzing: "Analizando",
  consolidating: "Consolidando",
  completed: "Completado",
};

function parseCountedProgress(text: string): { prefix: string; done: number; total: number } | null {
  const match = text.match(/^(.+?)\s*\((\d+)\s+de\s+(\d+)\)$/);
  if (!match) return null;
  return { prefix: match[1].trim(), done: parseInt(match[2]), total: parseInt(match[3]) };
}

export function ProgressBar({ stage, progress, stageProgress }: ProgressBarProps) {
  const [displayProgress, setDisplayProgress] = useState(progress);
  const [simulatedDone, setSimulatedDone] = useState(0);
  const progressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Real progress from backend always wins, salvo que sea una corrida nueva (queued): ahí se
  // reinicia a 0 en vez de conservar el % simulado de la corrida anterior (bug real: aprobar
  // fase 2 después de que "analyzing" ya había simulado hasta 75% dejaba el próximo arranque
  // pegado en 75% porque Math.max(75, 0) nunca vuelve a bajar). Mismo fix que ya tiene el
  // ProgressBar de la pestaña de detalle (components/analysis/ProgressBar.tsx).
  useEffect(() => {
    setDisplayProgress((prev) => (stage === "queued" ? 0 : Math.max(prev, progress)));
  }, [progress, stage]);

  // Simulate slow progress % during analyzing stage so the bar doesn't appear frozen
  useEffect(() => {
    if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
    if (stage !== "analyzing") return;

    progressIntervalRef.current = setInterval(() => {
      setDisplayProgress((prev) => (prev >= 75 ? prev : Math.min(75, prev + 1)));
    }, 1000);

    return () => {
      if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
    };
  }, [stage]);

  // Simulate category count because parallel analysis never sends intermediate updates
  useEffect(() => {
    if (doneIntervalRef.current) clearInterval(doneIntervalRef.current);
    setSimulatedDone(0);
    if (stage !== "analyzing") return;

    const parsed = stageProgress ? parseCountedProgress(stageProgress) : null;
    if (!parsed) return;

    const { total } = parsed;
    doneIntervalRef.current = setInterval(() => {
      setSimulatedDone((prev) => (prev >= total - 1 ? prev : prev + 1));
    }, 2500);

    return () => {
      if (doneIntervalRef.current) clearInterval(doneIntervalRef.current);
    };
  }, [stage, stageProgress]);

  const safeProgress = Math.max(0, Math.min(100, Math.round(displayProgress)));
  const stageLabel = STAGE_LABELS[stage] ?? stage;

  // Show simulated category count when the backend can't report partial progress
  let displayStageProgress = stageProgress;
  if (stageProgress && stage === "analyzing") {
    const parsed = parseCountedProgress(stageProgress);
    if (parsed) {
      const displayDone = Math.max(parsed.done, simulatedDone);
      displayStageProgress = `${parsed.prefix} (${displayDone} de ${parsed.total})`;
    }
  }

  return (
    <div className="min-w-[150px]">
      <div className="mb-[5px] flex items-center justify-between gap-2">
        <span className="truncate text-[13px] text-cedi-navy-68">{displayStageProgress || stageLabel}</span>
        <span className="text-[13px] font-bold text-cedi-navy">{safeProgress}%</span>
      </div>
      <div className="h-[6px] w-full rounded-full bg-cedi-navy-10">
        <div
          className="h-[6px] rounded-full bg-gradient-to-r from-cedi-celeste to-cedi-mint transition-all"
          style={{ width: `${safeProgress}%` }}
        />
      </div>
    </div>
  );
}
