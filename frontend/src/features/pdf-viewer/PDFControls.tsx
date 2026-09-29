import type { ReactNode } from "react";
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
  /** Nav de citas ("Cita X de Y"), compuesto en la misma barra de herramientas
   * en vez de tener su propia franja completa, igual al patrón `metaSlot` de
   * `ProgressBar`. */
  citationSlot?: ReactNode;
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
  citationSlot,
}: PDFControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-[rgba(0,60,107,.12)] bg-[#F4F9FC] px-3 py-2">
      <button
        type="button"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage <= 1}
        className="flex h-[30px] w-[30px] items-center justify-center rounded-lg text-[#003C6B] transition-colors hover:bg-white disabled:opacity-40"
        aria-label="Página anterior"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      <span className="font-display text-xs font-semibold text-[#003C6B]">
        Pág. {currentPage} / {totalPages || 1}
      </span>

      <button
        type="button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={totalPages === 0 || currentPage >= totalPages}
        className="flex h-[30px] w-[30px] items-center justify-center rounded-lg text-[#003C6B] transition-colors hover:bg-white disabled:opacity-40"
        aria-label="Página siguiente"
      >
        <ChevronRight className="h-4 w-4" />
      </button>

      {citationSlot}

      <div className="ml-auto flex items-center gap-0.5">
        <button
          type="button"
          onClick={onFitToWidth}
          disabled={isFitMode}
          className="flex h-[30px] w-[30px] items-center justify-center rounded-lg text-[#003C6B] transition-colors hover:bg-white disabled:opacity-40"
          aria-label="Ajustar al ancho"
          title="Ajustar al ancho"
        >
          <Scan className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={onZoomOut}
          disabled={zoom <= 0.5}
          className="flex h-[30px] w-[30px] items-center justify-center rounded-lg text-[#003C6B] transition-colors hover:bg-white disabled:opacity-40"
          aria-label="Reducir zoom"
        >
          <Minus className="h-4 w-4" />
        </button>
        <span className="font-display min-w-[40px] text-center text-xs font-semibold text-[#003C6B]">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={onZoomIn}
          disabled={zoom >= 2}
          className="flex h-[30px] w-[30px] items-center justify-center rounded-lg text-[#003C6B] transition-colors hover:bg-white disabled:opacity-40"
          aria-label="Aumentar zoom"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
