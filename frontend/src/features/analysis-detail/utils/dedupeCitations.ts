import { normalizeText } from "../../../utils/highlightText";
import type { Citation, NarrativeSource } from "../types";

interface SourceLike {
  document_id: string;
  page: number;
  text: string;
}

/**
 * Dos citas se consideran "la misma fuente" cuando comparten documento,
 * página, y el texto de una es igual o subcadena del texto de la otra —
 * mismo criterio que la síntesis del backend usa para deduplicar
 * (`prompts/_response_base.txt`, regla 5) y que `isPartOfCitation` usa para
 * resaltar en el visor de PDF: dos citas que se solapan en el mismo párrafo
 * terminan resaltando exactamente el mismo texto, así que mostrarlas como
 * fuentes separadas es ruido, no información nueva.
 */
function isSameSource(a: SourceLike, b: SourceLike): boolean {
  if (a.document_id !== b.document_id || a.page !== b.page) {
    return false;
  }
  const normalizedA = normalizeText(a.text);
  const normalizedB = normalizeText(b.text);
  if (normalizedA === "" || normalizedB === "") {
    return normalizedA === normalizedB;
  }
  return normalizedA.includes(normalizedB) || normalizedB.includes(normalizedA);
}

/**
 * Backstop de frontend: aunque el backend ya debería deduplicar las fuentes al
 * armar la narrativa, esto garantiza que la lista de "Fuentes verificables"
 * nunca repita la misma cita (ni una que solape con otra ya lista), incluso
 * si distintos ítems la citaron por separado. Ante un solapamiento, se
 * conserva el texto más largo (el que da más contexto y cubre el resaltado
 * más completo).
 */
function dedupeSources<T extends SourceLike>(sources: T[]): T[] {
  const result: T[] = [];

  for (const source of sources) {
    const matchIndex = result.findIndex((kept) => isSameSource(kept, source));
    if (matchIndex === -1) {
      result.push(source);
      continue;
    }
    if (source.text.trim().length > result[matchIndex].text.trim().length) {
      result[matchIndex] = source;
    }
  }

  return result;
}

export function dedupeCitations(citations: Citation[]): Citation[] {
  return dedupeSources(citations);
}

/** Misma deduplicación, para la lista `sources` de una CategoryNarrative. */
export function dedupeNarrativeSources(sources: NarrativeSource[]): NarrativeSource[] {
  return dedupeSources(sources);
}
