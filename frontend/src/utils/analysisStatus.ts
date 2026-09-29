// Unica fuente de verdad para "que status de Analysis cuenta como en curso".
// Bug real (2026-09-29): useAnalysesQuery tenia su propia copia de esta lista
// sin "processing" -- el polling del Home se cortaba apenas el analisis
// pasaba de queued a processing (el status real que usa el pipeline de
// extraccion), y la barra de progreso quedaba congelada hasta que el usuario
// recargaba la pagina a mano. "analyzing" NO es un status real de `Analysis`
// (solo lo usaba `run_analysis_stub`, un stub muerto ya eliminado del
// backend) -- no confundir con `current_stage: "analyzing"`, que sigue vivo.
export function isRunningAnalysisStatus(status: string): boolean {
  return status === "queued" || status === "processing";
}
