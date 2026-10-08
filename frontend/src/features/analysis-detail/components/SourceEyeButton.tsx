import { Eye } from "lucide-react";

interface SourceEyeButtonProps {
  /** Páginas del pliego a las que lleva. Sólo se usa para el rótulo accesible. */
  pages: number[];
  onClick: () => void;
  /** "default" (el chip con "pág. N", uso normal en listas de ítems) o "icon"
   * (solo el ojo, gris, sin texto ni borde -- para un único valor puntual
   * como el presupuesto oficial del encabezado, donde un chip con texto
   * compite visualmente con el propio valor). */
  variant?: "default" | "icon";
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
export function SourceEyeButton({ pages, onClick, variant = "default" }: SourceEyeButtonProps) {
  const unicas = Array.from(new Set(pages)).sort((a, b) => a - b);
  const etiqueta =
    unicas.length === 1
      ? `Ver fuente en el pliego (pág. ${unicas[0]})`
      : `Ver fuentes en el pliego (págs. ${unicas.join(", ")})`;

  if (variant === "icon") {
    return (
      <button
        type="button"
        data-testid="item-source-button"
        aria-label={etiqueta}
        title={etiqueta}
        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-0 bg-transparent text-[rgba(0,60,107,.4)] transition-colors hover:text-[#0099DB] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#0099DB]"
        onClick={onClick}
      >
        <Eye className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }

  const paginaLabel = unicas.length === 1 ? `pág. ${unicas[0]}` : `págs. ${unicas.join(", ")}`;

  return (
    <button
      type="button"
      data-testid="item-source-button"
      aria-label={etiqueta}
      title={etiqueta}
      className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2.5 text-xs font-semibold text-[#0099DB] transition-colors hover:border-[#0099DB] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#0099DB]"
      onClick={onClick}
    >
      <Eye className="h-3.5 w-3.5" aria-hidden="true" />
      <span>{paginaLabel}</span>
    </button>
  );
}
