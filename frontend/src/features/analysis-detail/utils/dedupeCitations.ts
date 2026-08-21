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

export interface DedupedNarrativeSources {
  sources: NarrativeSource[];
  /** id original -> id que quedó en `sources` tras la deduplicación. Incluye
   * una entrada para TODO id de entrada (incluso los que no se fusionaron,
   * mapeados a sí mismos) para que el llamador siempre pueda remapear
   * `source_ids` con un simple `idMapping.get(id) ?? id`. */
  idMapping: Map<number, number>;
}

/**
 * Misma deduplicación que `dedupeSources`, pero para `NarrativeSource`
 * (que sí tiene `id`): además de deduplicar, devuelve el mapping id
 * original -> id conservado. Sin este mapping, un bloque cuyo `source_ids`
 * apuntaba a una fuente que terminó fusionada en otra queda apuntando a un id
 * que ya no existe en la lista final -- una fuente que existía se vuelve
 * invisible para ese bloque en vez de mostrarse bajo el id que sobrevivió.
 */
export function dedupeNarrativeSources(sources: NarrativeSource[]): DedupedNarrativeSources {
  const result: NarrativeSource[] = [];
  const idMapping = new Map<number, number>();

  for (const source of sources) {
    const matchIndex = result.findIndex((kept) => isSameSource(kept, source));
    if (matchIndex === -1) {
      result.push(source);
      idMapping.set(source.id, source.id);
      continue;
    }

    const kept = result[matchIndex];
    if (source.text.trim().length > kept.text.trim().length) {
      result[matchIndex] = source;
      // Todo id que ya apuntaba a la fuente conservada anterior ahora tiene
      // que apuntar a la nueva (más larga), no quedarse huérfano.
      for (const [originalId, mappedId] of idMapping) {
        if (mappedId === kept.id) {
          idMapping.set(originalId, source.id);
        }
      }
    }
    idMapping.set(source.id, result[matchIndex].id);
  }

  return { sources: result, idMapping };
}

/** Remapea `source_ids` con el mapping que devuelve `dedupeNarrativeSources`,
 * preservando cualquier id que por algún motivo no esté en el mapping. */
export function remapSourceIds(sourceIds: number[], idMapping: Map<number, number>): number[] {
  return sourceIds.map((id) => idMapping.get(id) ?? id);
}
