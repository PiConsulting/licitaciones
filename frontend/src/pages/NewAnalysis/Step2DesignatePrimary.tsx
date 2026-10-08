import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";

import { DocumentList } from "../../components/upload/DocumentList";
import type { UploadedFile } from "../../types/upload";

interface Step2DesignatePrimaryProps {
  files: UploadedFile[];
  onBack: () => void;
  onNext: (primaryIndex: number) => void;
}

export function Step2DesignatePrimary({ files, onBack, onNext }: Step2DesignatePrimaryProps) {
  const [primaryIndex, setPrimaryIndex] = useState<number | null>(files.length === 1 ? 0 : null);

  useEffect(() => {
    if (files.length === 1) {
      onNext(0);
    }
  }, [files, onNext]);

  if (files.length === 0) {
    return (
      <section className="rounded-2xl border border-cedi-navy-12 bg-white p-6">
        <p className="text-sm text-cedi-navy-68">No hay documentos para designar.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4 rounded-2xl border border-cedi-navy-12 bg-white p-6" aria-label="Paso 2: Designar principal">
      <div>
        <h2 className="font-display text-xl font-semibold text-cedi-navy">¿Cuál es el pliego principal?</h2>
        <p className="mt-1.5 text-sm text-cedi-navy-68">El resto se trata como anexos. Las citas y el visor PDF arrancan por el principal.</p>
      </div>

      <DocumentList files={files} selectedIndex={primaryIndex} onSelect={setPrimaryIndex} />

      <div className="flex justify-between">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex h-11 items-center rounded-full border-2 border-[rgba(0,60,107,.2)] bg-white px-6 text-sm font-semibold text-[#003C6B] transition-colors hover:border-[#003C6B]"
        >
          Volver
        </button>
        <button
          type="button"
          onClick={() => {
            if (primaryIndex !== null) {
              onNext(primaryIndex);
            }
          }}
          disabled={primaryIndex === null}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-full border-0 bg-[linear-gradient(90deg,#2F4EF8,#A966FF)] px-[26px] text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          Siguiente
          <ChevronRight size={16} strokeWidth={2.5} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
