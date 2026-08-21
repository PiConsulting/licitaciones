import { useEffect, useState } from "react";

import { Button } from "../../components/Button";
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
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <p className="text-sm text-gray-600">No hay documentos para designar.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Paso 2: Designar documento principal</h2>
        <p className="mt-2 text-sm text-gray-600">Seleccioná cuál es el pliego principal (no anexos).</p>
      </div>

      <DocumentList files={files} selectedIndex={primaryIndex} onSelect={setPrimaryIndex} />

      <div className="flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack}>
          Volver
        </Button>
        <Button
          type="button"
          onClick={() => {
            if (primaryIndex !== null) {
              onNext(primaryIndex);
            }
          }}
          disabled={primaryIndex === null}
        >
          Siguiente
        </Button>
      </div>
    </section>
  );
}
