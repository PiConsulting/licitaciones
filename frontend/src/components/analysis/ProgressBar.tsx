import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

const STAGE_DISPLAY_NAMES: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Preparando para análisis",
  analyzing: "Analizando categorias",
  consolidating: "Consolidando",
  completed: "Analizado",
};

interface ProgressBarProps {
  stage: string;
  progress: number;
  isProcessing: boolean;
  stageProgress?: string | null;
}

function parseCountedProgress(text: string): { prefix: string; done: number; total: number } | null {
  const match = text.match(/^(.+?)\s*\((\d+)\s+de\s+(\d+)\)$/);
  if (!match) return null;
  return { prefix: match[1].trim(), done: parseInt(match[2]), total: parseInt(match[3]) };
}

export function ProgressBar({ stage, progress, isProcessing, stageProgress }: ProgressBarProps) {
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
    if (stage !== "analyzing" || !isProcessing) return;

    progressIntervalRef.current = setInterval(() => {
      setDisplayProgress((prev) => (prev >= 75 ? prev : Math.min(75, prev + 1)));
    }, 1000);

    return () => {
      if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
    };
  }, [stage, isProcessing]);

  // Simulate category count because parallel analysis never sends intermediate updates
  useEffect(() => {
    if (doneIntervalRef.current) clearInterval(doneIntervalRef.current);
    setSimulatedDone(0);
    if (stage !== "analyzing" || !isProcessing) return;

    const parsed = stageProgress ? parseCountedProgress(stageProgress) : null;
    if (!parsed) return;

    const { total } = parsed;
    doneIntervalRef.current = setInterval(() => {
      setSimulatedDone((prev) => (prev >= total - 1 ? prev : prev + 1));
    }, 2500);

    return () => {
      if (doneIntervalRef.current) clearInterval(doneIntervalRef.current);
    };
  }, [stage, isProcessing, stageProgress]);

  const stageName = STAGE_DISPLAY_NAMES[stage] || stage;
  const clampedProgress = Math.max(0, Math.min(100, Math.round(displayProgress)));

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
    <div className="space-y-2 rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {isProcessing ? <Loader2 className="h-4 w-4 animate-spin text-blue-500" /> : null}
          <span className="text-sm font-semibold text-gray-800">{stageName}</span>
        </div>
        <span className="text-sm text-gray-600">{clampedProgress}%</span>
      </div>

      {displayStageProgress ? <p className="text-xs text-gray-600">{displayStageProgress}</p> : null}

      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full bg-blue-500 transition-all duration-500 ease-out"
          style={{ width: `${clampedProgress}%` }}
        />
      </div>
    </div>
  );
}
