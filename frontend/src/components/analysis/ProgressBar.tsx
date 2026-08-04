import { Loader2 } from "lucide-react";

const STAGE_DISPLAY_NAMES: Record<string, string> = {
  queued: "En cola",
  extracting_text: "Extrayendo texto",
  indexing: "Indexando",
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

export function ProgressBar({ stage, progress, isProcessing, stageProgress }: ProgressBarProps) {
  const stageName = STAGE_DISPLAY_NAMES[stage] || stage;

  return (
    <div className="space-y-2 rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {isProcessing ? <Loader2 className="h-4 w-4 animate-spin text-blue-500" /> : null}
          <span className="text-sm font-semibold text-gray-800">{stageName}</span>
        </div>
        <span className="text-sm text-gray-600">{progress}%</span>
      </div>

      {stageProgress ? <p className="text-xs text-gray-600">{stageProgress}</p> : null}

      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full bg-blue-500 transition-all duration-500 ease-out"
          style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
        />
      </div>
    </div>
  );
}
