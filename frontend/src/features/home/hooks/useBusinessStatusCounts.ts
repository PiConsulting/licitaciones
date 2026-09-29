export interface BusinessStatusCounts {
  noAprobadas: number;
  enRevision: number;
  presentadas: number;
  ganadas: number;
  perdidas: number;
}

/**
 * Punto de integración para FE5.4.
 * Mientras no exista el endpoint real, devuelve conteos neutros explícitos.
 */
export function useBusinessStatusCounts(): BusinessStatusCounts {
  return {
    noAprobadas: 0,
    enRevision: 0,
    presentadas: 0,
    ganadas: 0,
    perdidas: 0,
  };
}
