import { Eye } from "lucide-react";

export interface SourceReferenceProps {
  /** ID del documento fuente */
  documentId: string;
  /** Número de página donde está la fuente */
  pageNumber: number;
  /** Fragmento de texto citado (opcional) */
  fragment?: string;
  /** Callback para abrir el visor PDF */
  onView?: () => void;
}

/**
 * Componente reutilizable para mostrar referencias a fuentes verificables
 * en documentos. Muestra la página y fragmento de texto, con un botón para
 * abrir el visor PDF en la ubicación exacta.
 * 
 * Usado en EventDetailModal y DeadlineDetailModal para mantener consistencia
 * en la UX de acceso a fuentes.
 */
export function SourceReference({ pageNumber, fragment, onView }: SourceReferenceProps) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-700 mb-3">
        Fuente en el documento
      </h4>
      <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-600 mb-1">
              Página {pageNumber}
            </p>
            {fragment && (
              <p className="text-sm text-gray-800 italic line-clamp-3">
                &quot;{fragment}&quot;
              </p>
            )}
          </div>
          {onView && (
            <button
              type="button"
              onClick={onView}
              aria-label={`Ver fuente en el pliego (pág. ${pageNumber})`}
              title={`Ver fuente en el pliego (pág. ${pageNumber})`}
              className="shrink-0 rounded p-1.5 text-gray-400 transition-colors hover:text-primary hover:bg-gray-100 focus:text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              data-testid="source-reference-view-button"
            >
              <Eye className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
