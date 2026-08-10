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

  // Real progress from backend always wins
  useEffect(() => {
    setDisplayProgress((prev) => Math.max(prev, progress));
  }, [progress]);

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
    <div className="w-full min-w-40">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-gray-600">{displayStageProgress || stageLabel}</span>
        <span className="text-xs font-semibold text-gray-700">{safeProgress}%</span>
      </div>
      <div className="h-2 w-full rounded bg-gray-100">
        <div className="h-2 rounded bg-primary transition-all" style={{ width: `${safeProgress}%` }} />
      </div>
    </div>
  );
}
