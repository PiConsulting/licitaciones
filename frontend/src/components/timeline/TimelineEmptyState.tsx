import { Calendar } from "lucide-react";
import { Button } from "../Button";

interface TimelineEmptyStateProps {
  onAddEvent: () => void;
}

export function TimelineEmptyState({ onAddEvent }: TimelineEmptyStateProps) {
  return (
    <div className="timeline-empty-state flex flex-col items-center justify-center py-16 px-4">
      <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-gray-100">
        <Calendar className="h-12 w-12 text-gray-400" />
      </div>

      <h3 className="mb-2 text-lg font-semibold text-gray-900">
        No se encontraron eventos temporales
      </h3>

      <p className="mb-6 max-w-md text-center text-sm text-gray-600">
        El análisis IA no detectó eventos o plazos temporales en los documentos. Podés agregar
        eventos manualmente para construir la línea de tiempo del proceso.
      </p>

      <Button variant="primary" onClick={onAddEvent}>
        Agregar evento
      </Button>
    </div>
  );
}
