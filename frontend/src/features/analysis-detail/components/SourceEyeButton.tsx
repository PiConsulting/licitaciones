import { Eye } from "lucide-react";

interface SourceEyeButtonProps {
  /** Páginas del pliego a las que lleva. Sólo se usa para el rótulo accesible. */
  pages: number[];
  onClick: () => void;
}

/**
 * Botón de evidencia por ítem: un ojo chico, sin texto ni borde, que sólo toma
 * color al pasar por encima. Tiene que poder ignorarse mientras se lee y estar
 * ahí cuando se lo busca.
 *
 * Vive en su propio archivo porque lo usan `NarrativeBlocks` (bullets y filas)
 * y `PlazosTimeline` (hitos). Este último tenía un `ActionButton` con el texto
 * "Ver fuente": 36px de alto, con borde y fondo, uno por hito — en una lista de
 * diez plazos, la columna de botones pesaba más que los plazos.
 */
export function SourceEyeButton({ pages, onClick }: SourceEyeButtonProps) {
  const unicas = Array.from(new Set(pages)).sort((a, b) => a - b);
  const etiqueta =
    unicas.length === 1
      ? `Ver fuente en el pliego (pág. ${unicas[0]})`
      : `Ver fuentes en el pliego (págs. ${unicas.join(", ")})`;

  return (
    <button
      type="button"
      data-testid="item-source-button"
      aria-label={etiqueta}
      title={etiqueta}
      className="mt-0.5 shrink-0 rounded p-0.5 text-gray-300 transition-colors hover:text-primary focus:text-primary focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
      onClick={onClick}
    >
      <Eye className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}
