/**
 * Highlight basado en coordenadas pre-computadas en el backend.
 */

interface HighlightRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface HighlightOverlayProps {
  regions: HighlightRegion[];
  /** Escala EFECTIVA de la página renderizada respecto de su tamaño nativo en
   * puntos (`page.width / page.originalWidth`). No es el zoom que eligió el
   * usuario: en modo ancho-de-columna react-pdf renderiza a una escala que el
   * componente nunca fijó. */
  scale: number;
}

/**
 * Dibuja los rectángulos de resaltado sobre una página del PDF.
 *
 * CONTRATO DE COORDENADAS (FIX HL-01, auditoría 2026-08-13)
 * ---------------------------------------------------------
 * El backend (`analysis/extraction/highlight.py`) emite cada región con:
 *   - origen ARRIBA-IZQUIERDA de la página (el de PyMuPDF y el de CSS),
 *   - unidades en PUNTOS de la página SIN escalar,
 *   - `y` = borde superior del rectángulo.
 *
 * Por lo tanto lo único que corresponde hacer acá es multiplicar por la escala.
 *
 * Antes se aplicaba `pageHeight - region.y - region.height` con la altura YA
 * renderizada. Eso era una segunda inversión de eje: el backend también
 * invertía, así que las dos juntas se cancelaban -- pero SÓLO con scale === 1.
 * Con cualquier otra escala (y el visor arranca en ancho-de-columna, que casi
 * nunca es 1) el recuadro caía en otro renglón, o fuera de la página.
 */
export function HighlightOverlay({ regions, scale }: HighlightOverlayProps): JSX.Element | null {
  if (!regions || regions.length === 0 || !scale || scale <= 0) {
    return null;
  }

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 1,
      }}
    >
      {regions.map((region, index) => (
        <div
          key={index}
          style={{
            position: 'absolute',
            left: `${region.x * scale}px`,
            top: `${region.y * scale}px`,
            width: `${region.width * scale}px`,
            height: `${region.height * scale}px`,
            backgroundColor: 'rgba(250, 204, 21, 0.35)',
            pointerEvents: 'none',
            border: '1px solid rgba(250, 204, 21, 0.6)',
          }}
        />
      ))}
    </div>
  );
}

/**
 * Combina highlight_regions de múltiples sources para una página.
 * 
 * @param sources - Lista de sources que apuntan a esta página
 * Deduplica regiones idénticas.
 */
export function getCombinedHighlightRegions(
  sources: Array<{ page: number; highlight_regions?: HighlightRegion[] }>,
  pageNumber: number
): HighlightRegion[] {
  const regions: HighlightRegion[] = [];
  
  for (const source of sources) {
    if (source.page === pageNumber && source.highlight_regions) {
      regions.push(...source.highlight_regions);
    }
  }
  
  const seen = new Set<string>();
  return regions.filter((region) => {
    const key = `${region.x},${region.y},${region.width},${region.height}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}


