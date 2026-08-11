/**
 * Highlight basado en coordenadas pre-computadas en el backend.
 * 
 * FIX CRÍTICO (2026-08): Reemplaza el sistema de heurísticas frágiles de
 * highlightText.ts con coordenadas exactas calculadas usando PyMuPDF.
 * 
 * Este módulo maneja el rendering de rectangles de highlight sobre el canvas
 * del PDF usando las coordenadas que vienen en source.highlight_regions.
 */

interface HighlightRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface HighlightOverlayProps {
  regions: HighlightRegion[];
  scale: number;
  pageHeight: number;
}

/**
 * Dibuja un highlight overlay sobre una página del PDF.
 * 
 * NOTA: PyMuPDF usa coordenadas bottom-left origin, pero react-pdf usa
 * top-left origin. Necesitamos transformar las coordenadas.
 * 
 * @param regions - Regiones de highlight (output de backend)
 * @param scale - Factor de escala actual del PDF
 * @param pageHeight - Altura de la página en puntos (para transformar Y)
 */
export function HighlightOverlay({ regions, scale, pageHeight }: HighlightOverlayProps): JSX.Element {
  if (!regions || regions.length === 0) {
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
      {regions.map((region, index) => {
        // Transformar coordenadas de PyMuPDF (bottom-left) a react-pdf (top-left)
        const transformedY = pageHeight - region.y - region.height;
        
        return (
          <div
            key={index}
            style={{
              position: 'absolute',
              left: `${region.x * scale}px`,
              top: `${transformedY * scale}px`,
              width: `${region.width * scale}px`,
              height: `${region.height * scale}px`,
              backgroundColor: 'rgba(250, 204, 21, 0.35)', // Mismo color que antes
              pointerEvents: 'none',
              // Borde sutil para mejor visibilidad
              border: '1px solid rgba(250, 204, 21, 0.6)',
            }}
          />
        );
      })}
    </div>
  );
}

/**
 * Combina highlight_regions de múltiples sources para una página.
 * 
 * @param sources - Lista de sources que apuntan a esta página
 * @param pageNumber - Número de página (1-indexed)
 */
export function getCombinedHighlightRegions(
  sources: Array<{ page_number: number; highlight_regions?: HighlightRegion[] }>,
  pageNumber: number
): HighlightRegion[] {
  const regions: HighlightRegion[] = [];
  
  for (const source of sources) {
    if (source.page_number === pageNumber && source.highlight_regions) {
      regions.push(...source.highlight_regions);
    }
  }
  
  // Deduplicar regiones overlapping exactas (mismo x, y, width, height)
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

/**
 * Determina si una source tiene highlights disponibles.
 * 
 * IMPORTANTE: Si highlight_regions está vacío, puede significar:
 * 1. PyMuPDF no está instalado en el backend
 * 2. La citation no se encontró en el PDF (error de extracción)
 * 3. El análisis es anterior al fix de highlights
 * 
 * El frontend debe manejar este caso mostrando la página pero sin highlight.
 */
export function hasHighlightRegions(source: { highlight_regions?: HighlightRegion[] }): boolean {
  return Array.isArray(source.highlight_regions) && source.highlight_regions.length > 0;
}
