import { useState, useEffect, useRef } from "react";
import { ArrowRight } from "lucide-react";
import { Badge, BadgeTone } from "../Badge";
import { Button } from "../Button";
import type { DeadlineResponse, EventResponse, CalculationStatus } from "../../types/timeline";
import { formatEventDate } from "../../utils/dates";
import { SourceReference } from "./SourceReference";

interface DeadlineDetailModalProps {
  deadline: DeadlineResponse;
  triggerEvent?: EventResponse;
  targetEvent?: EventResponse;
  open: boolean;
  onClose: () => void;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const STATUS_CONFIG: Record<CalculationStatus, { label: string; tone: BadgeTone }> = {
  calculated: { label: "Calculada", tone: "success" },
  pending: { label: "Pendiente", tone: "neutral" },
  error: { label: "Error", tone: "error" },
};

const DAY_TYPE_LABEL: Record<string, string> = {
  corridos: "corridos",
  hábiles: "hábiles",
  no_especificado: "(tipo no especificado)",
};

export function DeadlineDetailModal({
  deadline,
  triggerEvent,
  targetEvent,
  open,
  onClose,
  onViewSource,
}: DeadlineDetailModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const statusConfig = STATUS_CONFIG[deadline.calculation_status];
  const dayTypeLabel = DAY_TYPE_LABEL[deadline.day_type] || deadline.day_type;
  const hasError = deadline.calculation_status === "error";
  const hasSource = typeof deadline.source_document_id === 'string' && typeof deadline.source_page === 'number';

  const handleViewSource = () => {
    if (hasSource && onViewSource) {
      onViewSource(deadline.source_document_id, deadline.source_page, deadline.source_fragment);
    }
  };

  // Focus trap implementation
  useEffect(() => {
    if (open && modalRef.current) {
      const previousActiveElement = document.activeElement as HTMLElement;
      modalRef.current.focus();

      return () => {
        previousActiveElement?.focus();
      };
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div 
        ref={modalRef}
        tabIndex={-1}
        className="w-full max-w-2xl rounded-lg border border-gray-200 bg-white p-6 shadow-xl"
      >
        <h2 className="text-xl font-semibold text-gray-900">Detalle del plazo</h2>

        <div className="mt-6 space-y-6">
          {/* Estructura del Plazo */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-center gap-4 text-base">
              <div className="text-center flex-1">
                <div className="text-xs font-medium text-gray-600 mb-1 uppercase tracking-wide">
                  Evento disparador
                </div>
                <div className="font-semibold text-gray-900">{triggerEvent?.name || "Desconocido"}</div>
                <div className="text-sm text-gray-700 mt-1">
                  {triggerEvent?.event_date ? formatEventDate(triggerEvent.event_date) : "Fecha pendiente"}
                </div>
              </div>

              <div className="flex flex-col items-center px-4">
                <ArrowRight className="w-6 h-6 text-blue-600" />
                <div className="text-sm font-medium text-blue-900 mt-2 text-center">
                  {deadline.duration} {deadline.unit}
                  <br />
                  {dayTypeLabel}
                </div>
              </div>

              <div className="text-center flex-1">
                <div className="text-xs font-medium text-gray-600 mb-1 uppercase tracking-wide">
                  Evento resultado
                </div>
                <div className="font-semibold text-gray-900">{targetEvent?.name || deadline.name || "Desconocido"}</div>
                <div className="text-sm text-gray-700 mt-1">
                  {deadline.deadline_date ? formatEventDate(deadline.deadline_date) : "Pendiente"}
                </div>
              </div>
            </div>
          </div>

          {/* Estado del Cálculo */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Estado del cálculo</h4>
            <div className="flex items-center gap-2">
              <Badge tone={statusConfig.tone}>{statusConfig.label}</Badge>
              {hasError && deadline.calculation_error && (
                <span className="text-sm text-error">{deadline.calculation_error}</span>
              )}
            </div>
          </div>

          {/* Error de Cálculo */}
          {hasError && deadline.calculation_error && (
            <div className="bg-error-light border border-error rounded-lg p-3 flex items-start gap-2">
              <svg
                className="w-5 h-5 text-error flex-shrink-0 mt-0.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div className="text-sm text-error">
                <p className="font-medium">No se pudo calcular</p>
                <p className="mt-1">{deadline.calculation_error}</p>
              </div>
            </div>
          )}

          {/* Fuente Verificable */}
          {hasSource && (
            <SourceReference
              documentId={deadline.source_document_id!}
              pageNumber={deadline.source_page!}
              fragment={deadline.source_fragment}
              onView={onViewSource ? handleViewSource : undefined}
            />
          )}
        </div>

        {/* Acciones */}
        <div className="flex justify-end pt-6 border-t mt-6">
          <Button variant="secondary" onClick={onClose}>
            Cerrar
          </Button>
        </div>
      </div>
    </div>
  );
}
