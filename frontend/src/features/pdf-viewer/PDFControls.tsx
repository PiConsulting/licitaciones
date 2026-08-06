import { ChevronLeft, ChevronRight, Minus, Plus, Scan } from "lucide-react";

interface PDFControlsProps {
  currentPage: number;
  totalPages: number;
  zoom: number;
  isFitMode: boolean;
  onPageChange: (page: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitToWidth: () => void;
}

export function PDFControls({
  currentPage,
  totalPages,
  zoom,
  isFitMode,
  onPageChange,
  onZoomIn,
  onZoomOut,
  onFitToWidth,
}: PDFControlsProps) {
  return (
    <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 p-2">
      <button
        type="button"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage <= 1}
        className="rounded p-2 hover:bg-gray-200 disabled:opacity-40"
        aria-label="Página anterior"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      <span className="text-xs text-gray-700">Página {currentPage} de {totalPages || 1}</span>

      <button
        type="button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={totalPages === 0 || currentPage >= totalPages}
        className="rounded p-2 hover:bg-gray-200 disabled:opacity-40"
        aria-label="Página siguiente"
      >
        <ChevronRight className="h-4 w-4" />
      </button>

      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          onClick={onFitToWidth}
          disabled={isFitMode}
          className="rounded p-2 hover:bg-gray-200 disabled:opacity-40"
          aria-label="Ajustar al ancho"
          title="Ajustar al ancho"
        >
          <Scan className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onZoomOut}
          disabled={zoom <= 0.5}
          className="rounded p-2 hover:bg-gray-200 disabled:opacity-40"
          aria-label="Reducir zoom"
        >
          <Minus className="h-4 w-4" />
        </button>
        <span className="min-w-[3rem] text-center text-xs text-gray-700">{Math.round(zoom * 100)}%</span>
        <button
          type="button"
          onClick={onZoomIn}
          disabled={zoom >= 2}
          className="rounded p-2 hover:bg-gray-200 disabled:opacity-40"
          aria-label="Aumentar zoom"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
