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
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-3 py-2 text-xs">
      <button type="button" className="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40" onClick={onPrev} disabled={currentIndex <= 0}>
        ← Cita anterior
      </button>
      <span>{`Cita ${currentIndex + 1} de ${total}`}</span>
      <button
        type="button"
        className="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
        onClick={onNext}
        disabled={currentIndex >= total - 1}
      >
        Cita siguiente →
      </button>
    </div>
  );
}
