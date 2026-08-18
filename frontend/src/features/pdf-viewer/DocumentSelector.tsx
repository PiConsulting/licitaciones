import { useMemo, useState } from "react";

import type { ViewerDocument } from "./types";

interface DocumentSelectorProps {
  documents: ViewerDocument[];
  value: string;
  onChange: (documentId: string) => void;
}

const MAX_VISIBLE_CHIPS = 6;

function cleanFilename(filename: string): string {
  return filename.replace(/\.[^/.]+$/, "");
}

export function DocumentSelector({ documents, value, onChange }: DocumentSelectorProps) {
  const [expanded, setExpanded] = useState(false);

  if (documents.length <= 1) {
    return null;
  }

  const selectedDocument = documents.find((document) => document.id === value) ?? null;

  const visibleDocuments = useMemo(() => {
    if (expanded || documents.length <= MAX_VISIBLE_CHIPS) {
      return documents;
    }

    const base = documents.slice(0, MAX_VISIBLE_CHIPS);
    if (!selectedDocument) {
      return base;
    }

    const selectedAlreadyVisible = base.some((document) => document.id === selectedDocument.id);
    if (selectedAlreadyVisible) {
      return base;
    }

    return [...base.slice(0, MAX_VISIBLE_CHIPS - 1), selectedDocument];
  }, [documents, expanded, selectedDocument]);

  const hiddenCount = Math.max(0, documents.length - visibleDocuments.length);

  return (
    <div className="w-full min-w-0" data-testid="pdf-document-tabs-scroll">
      <div role="tablist" aria-label="Documentos del visor" className="flex flex-wrap items-center gap-1.5">
        {visibleDocuments.map((document) => {
          const isActive = document.id === value;
          return (
            <button
              key={document.id}
              type="button"
              role="tab"
              aria-pressed={isActive}
              aria-label={cleanFilename(document.filename)}
              onClick={() => onChange(document.id)}
              className={`inline-flex max-w-full items-center rounded-md border px-2.5 py-1 text-xs transition-colors ${
                isActive
                  ? "border-gray-900 bg-gray-900 text-white"
                  : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              <span className="max-w-48 truncate">{cleanFilename(document.filename)}</span>
            </button>
          );
        })}

        {hiddenCount > 0 && (
          <button
            type="button"
            className="inline-flex items-center rounded-md border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-50"
            onClick={() => setExpanded(true)}
            aria-label="Mostrar más documentos"
          >
            +{hiddenCount} más
          </button>
        )}

        {expanded && documents.length > MAX_VISIBLE_CHIPS && (
          <button
            type="button"
            className="inline-flex items-center rounded-md border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-50"
            onClick={() => setExpanded(false)}
            aria-label="Mostrar menos documentos"
          >
            Ver menos
          </button>
        )}
      </div>
    </div>
  );
}
