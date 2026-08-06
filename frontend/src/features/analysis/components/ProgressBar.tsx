interface ProgressBarProps {
  stage: string;
  progress: number;
  stageProgress?: string | null;
}

const STAGE_LABELS: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Indexando",
  analyzing: "Analizando",
  consolidating: "Consolidando",
  completed: "Completado",
};

export function ProgressBar({ stage, progress, stageProgress }: ProgressBarProps) {
  const safeProgress = Math.max(0, Math.min(100, progress));
  const stageLabel = STAGE_LABELS[stage] ?? stage;

  return (
    <div className="w-full min-w-40">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-gray-600">{stageProgress || stageLabel}</span>
        <span className="text-xs font-semibold text-gray-700">{safeProgress}%</span>
      </div>
      <div className="h-2 w-full rounded bg-gray-100">
        <div className="h-2 rounded bg-primary transition-all" style={{ width: `${safeProgress}%` }} />
      </div>
    </div>
  );
}
