/**
 * Une varias oraciones/hechos en una única cláusula enumerada dentro de un
 * mismo párrafo (ej. "(1) ...; (2) ...; y (3) ..."), en vez de una viñeta por
 * hecho — para categorías que tienen que mostrarse como una sola respuesta en
 * prosa en vez de una tarjeta por ítem.
 */
export function joinAsEnumeratedClause(sentences: string[]): string {
  const cleaned = sentences.map((sentence) => sentence.trim().replace(/[.;]+$/, "")).filter(Boolean);
  if (cleaned.length === 0) {
    return "";
  }
  if (cleaned.length === 1) {
    return `${cleaned[0]}.`;
  }
  const numbered = cleaned.map((sentence, index) => `(${index + 1}) ${sentence}`);
  const last = numbered.pop() as string;
  return `${numbered.join("; ")}; y ${last}.`;
}
