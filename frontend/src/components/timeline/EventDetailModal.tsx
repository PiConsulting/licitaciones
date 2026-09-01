import { useState, useEffect, useRef } from "react";
import { Badge, BadgeTone } from "../Badge";
import { Button } from "../Button";
import type { EventResponse, DeadlineResponse, DateSource } from "../../types/timeline";
import { EditDateModal } from "./EditDateModal";
import { DeleteEventDialog } from "./DeleteEventDialog";
import { formatEventDate } from "../../utils/dates";
import { SourceReference } from "./SourceReference";

interface EventDetailModalProps {
  event: EventResponse;
  deadlines?: DeadlineResponse[];
  open: boolean;
  onClose: () => void;
  onViewSource?: (documentId: string, page: number, fragment?: string) => void;
}

const DATE_SOURCE_CONFIG: Record<DateSource, { label: string; tone: BadgeTone }> = {
  detected: { label: "Detectada", tone: "info" },
  user_input: { label: "Ingresada", tone: "success" },
  calculated: { label: "Calculada", tone: "warning" },
  pending: { label: "Pendiente", tone: "neutral" },
};

export function EventDetailModal({
  event,
  deadlines = [],
  open,
  onClose,
  onViewSource,
}: EventDetailModalProps) {
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  const config = DATE_SOURCE_CONFIG[event.date_source];
  const hasSource = typeof event.source_document_id === 'string' && typeof event.source_page === 'number';
  const canEdit = true; // Todos los eventos pueden editarse
  const canDelete = event.date_source === "user_input"; // Solo los creados manualmente

  const handleViewSource = () => {
    if (hasSource && onViewSource) {
      onViewSource(event.source_document_id, event.source_page, event.source_fragment);
    }
  };

  // Reset nested modal states when main modal closes
  useEffect(() => {
    if (!open) {
      setShowEditModal(false);
      setShowDeleteDialog(false);
    }
  }, [open]);

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
    <>
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
          <h2 className="text-xl font-semibold text-gray-900">{event.name}</h2>

          <div className="mt-6 space-y-6">
            {/* Información Principal */}
            <div>
              <div className="flex items-center gap-3">
                <span className="text-lg font-medium text-gray-900">
                  {event.event_date ? formatEventDate(event.event_date) : "Fecha pendiente"}
                </span>
                <Badge tone={config.tone}>{config.label}</Badge>
              </div>
            </div>

            {/* Plazos Dependientes */}
            {deadlines.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-3">
                  Plazos que dependen de este evento
                </h4>
                <div className="space-y-2">
                  {deadlines.map((deadline) => (
                    <div
                      key={deadline.deadline_id}
                      className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-sm"
                    >
                      <span className="font-medium">{deadline.name}</span>
                      <span className="text-gray-600"> — </span>
                      <span className="text-gray-700">
                        {deadline.duration} {deadline.unit} {deadline.day_type}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Fuente Verificable */}
            {hasSource && (
              <SourceReference
                documentId={event.source_document_id!}
                pageNumber={event.source_page!}
                fragment={event.source_fragment}
                onView={onViewSource ? handleViewSource : undefined}
              />
            )}

            {/* Sin plazos dependientes ni fuente */}
            {deadlines.length === 0 && !hasSource && (
              <div className="text-sm text-gray-500 italic">
                Este evento no tiene plazos dependientes ni fuente verificable en el documento.
              </div>
            )}
          </div>

          {/* Acciones */}
          <div className="flex justify-between items-center pt-6 border-t mt-6">
            <div className="flex gap-2">
              {canEdit && (
                <Button variant="secondary" onClick={() => setShowEditModal(true)}>
                  Editar fecha
                </Button>
              )}
              {canDelete && (
                <Button variant="danger" onClick={() => setShowDeleteDialog(true)}>
                  Eliminar
                </Button>
              )}
            </div>
            <Button variant="secondary" onClick={onClose}>
              Cerrar
            </Button>
          </div>
        </div>
      </div>

      {showEditModal && (
        <EditDateModal event={event} open={showEditModal} onClose={() => setShowEditModal(false)} />
      )}

      {showDeleteDialog && (
        <DeleteEventDialog
          event={event}
          open={showDeleteDialog}
          onClose={() => setShowDeleteDialog(false)}
        />
      )}
    </>
  );
}
