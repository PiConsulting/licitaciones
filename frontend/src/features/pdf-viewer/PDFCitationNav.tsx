import { ChevronLeft, ChevronRight } from "lucide-react";

interface PDFCitationNavProps {
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}

export function PDFCitationNav({ currentIndex, total, onPrev, onNext }: PDFCitationNavProps) {
  if (total <= 1) {
    return null;
  }

  return (
    <div className="ml-2 flex items-center gap-0.5">
      <button
        type="button"
        onClick={onPrev}
        disabled={currentIndex <= 0}
        className="flex h-5 w-5 items-center justify-center rounded-full text-[#0B6B58] transition-colors hover:bg-[rgba(127,243,222,.5)] disabled:opacity-40"
        aria-label="Cita anterior"
      >
        <ChevronLeft className="h-3 w-3" strokeWidth={2.5} />
      </button>
      <span className="rounded-full bg-[rgba(127,243,222,.35)] px-2.5 py-1 text-[11px] font-semibold text-[#0B6B58]">
        {`Cita ${currentIndex + 1} de ${total}`}
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={currentIndex >= total - 1}
        className="flex h-5 w-5 items-center justify-center rounded-full text-[#0B6B58] transition-colors hover:bg-[rgba(127,243,222,.5)] disabled:opacity-40"
        aria-label="Cita siguiente"
      >
        <ChevronRight className="h-3 w-3" strokeWidth={2.5} />
      </button>
    </div>
  );
}
